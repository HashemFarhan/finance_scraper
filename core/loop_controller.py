from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

from core.crawler import Crawler
from core.models import ComplianceResult, FormCandidate, StepRecord
from detectors.form_detector import FormDetector
from extractors.consent_extractor import ConsentExtractor
from extractors.link_extractor import LinkExtractor
from extractors.policy_extractor import PolicyExtractor
from utils.url_utils import ensure_url_scheme
from vision.decision_engine import DecisionEngine
from vision.llm_client import LLMClient
from vision.screenshot_service import ScreenshotService
from core.navigator import Navigator


logger = logging.getLogger(__name__)


class LoopController:
    def __init__(
        self,
        max_steps: int = 5,
        max_runtime_seconds: int = 120,
        output_dir: Path | str = "runs",
        headless: bool = True,
        use_llm: bool = True,
        llm_model: str | None = None,
    ) -> None:
        self.max_steps = max_steps
        self.max_runtime_seconds = max_runtime_seconds
        self.output_dir = Path(output_dir)
        self.headless = headless
        self.use_llm = use_llm
        self.llm_model = llm_model

    async def run(self, url: str) -> ComplianceResult:
        source_url = ensure_url_scheme(url)
        steps: list[StepRecord] = []
        screenshots: list[str] = []
        errors: list[str] = []
        form_evidence: list[str] = []
        form_candidates: list[FormCandidate] = []
        primary_form_candidate: FormCandidate | None = None
        form_found = False

        llm_client = LLMClient(model=self.llm_model) if self.use_llm else None
        decision_engine = DecisionEngine(llm_client=llm_client)
        screenshot_service = ScreenshotService(self.output_dir)
        form_detector = FormDetector()
        navigator = Navigator()

        deadline = time.monotonic() + self.max_runtime_seconds

        async with Crawler(headless=self.headless) as crawler:
            page = await crawler.open(source_url)
            visited_states: set[str] = set()

            for index in range(self.max_steps):
                if time.monotonic() > deadline:
                    errors.append("Navigation stopped because max_runtime was reached.")
                    break

                artifacts = await screenshot_service.capture(page, step_index=index)
                artifact_paths = [artifact.path for artifact in artifacts]
                screenshots.extend(artifact_paths)

                detection = await form_detector.detect(page)
                if detection.found:
                    form_found = True
                    form_evidence = detection.evidence
                    form_candidates = detection.candidates
                    primary_form_candidate = detection.primary_candidate
                    steps.append(
                        StepRecord(
                            index=index,
                            url=page.url,
                            action="form_detected",
                            reason=self._form_reason(detection),
                            success=True,
                            screenshots=artifact_paths,
                        )
                    )
                    break

                state_key = await self._state_key(page)
                if state_key in visited_states:
                    errors.append("Navigation stopped after detecting a repeated page state.")
                    break
                visited_states.add(state_key)

                decision = await decision_engine.decide(page, artifacts, current_url=page.url)
                if decision.action == "form_visible":
                    form_found = True
                    steps.append(
                        StepRecord(
                            index=index,
                            url=page.url,
                            action="form_visible",
                            reason=decision.reason or "LLM reported that the form is visible.",
                            success=True,
                            screenshots=artifact_paths,
                        )
                    )
                    break

                if decision.action != "click" or not decision.text:
                    steps.append(
                        StepRecord(
                            index=index,
                            url=page.url,
                            action="none",
                            reason=decision.reason or "No viable navigation action found.",
                            success=True,
                            screenshots=artifact_paths,
                        )
                    )
                    break

                click_result = await navigator.click_best_candidate(page, decision.text)
                steps.append(
                    StepRecord(
                        index=index,
                        url=page.url,
                        action="click",
                        target=click_result.text or decision.text,
                        reason=decision.reason,
                        success=click_result.success,
                        error=click_result.error,
                        screenshots=artifact_paths,
                    )
                )
                if not click_result.success:
                    errors.append(click_result.error or f"Unable to click {decision.text!r}.")
                    break

                await crawler.wait_for_stable_page(page)

            final_detection = await form_detector.detect(page)
            if final_detection.found:
                form_found = True
                form_evidence = final_detection.evidence
                form_candidates = final_detection.candidates
                primary_form_candidate = final_detection.primary_candidate

            consent = None
            links = None
            terms_doc = None
            privacy_doc = None

            if form_found:
                consent = await ConsentExtractor().extract(page)
                links = await LinkExtractor().extract(page)
                if crawler.context:
                    policy_extractor = PolicyExtractor(crawler.context)
                    terms_doc = await policy_extractor.extract(links.terms_url)
                    privacy_doc = await policy_extractor.extract(links.privacy_url)

            policy_errors = [
                doc.error
                for doc in (terms_doc, privacy_doc)
                if doc is not None and doc.error is not None
            ]
            errors.extend(policy_errors)

            return ComplianceResult(
                form_found=form_found,
                final_url=page.url,
                steps=steps,
                screenshots=screenshots,
                submit_language=consent.submit_language if consent else None,
                consent_evidence=consent.evidence if consent else [],
                terms_url=links.terms_url if links else None,
                privacy_url=links.privacy_url if links else None,
                terms_text=terms_doc.text if terms_doc else None,
                privacy_text=privacy_doc.text if privacy_doc else None,
                link_evidence=links.evidence if links else [],
                form_evidence=form_evidence,
                form_candidates=form_candidates,
                primary_form_candidate=primary_form_candidate,
                errors=errors,
            )

    async def _state_key(self, page) -> str:
        visible_text = await page.evaluate(
            "() => document.body ? document.body.innerText.slice(0, 4000) : ''"
        )
        digest = hashlib.sha1(f"{page.url}\n{visible_text}".encode("utf-8")).hexdigest()
        return digest

    def _form_reason(self, detection) -> str:
        if detection.primary_candidate:
            candidate = detection.primary_candidate
            return (
                "Form detector selected "
                f"{candidate.kind} {candidate.selector!r}: {candidate.reason}"
            )
        return "Form detector found inputs or submit controls."
