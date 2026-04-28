from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Any

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
        if llm_client and llm_client.enabled:
            return await self._run_llm_guided(source_url, llm_client)
        if self.use_llm:
            return ComplianceResult(
                form_found=False,
                final_url=source_url,
                steps=[],
                screenshots=[],
                decision_source="llm_not_configured",
                errors=[
                    "LLM navigation is enabled, but no OpenAI API key is configured. "
                    "Set OPENAI_API_KEY in the environment or config/local_settings.py."
                ],
            )

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
                decision_source="legacy_dom_heuristic",
                errors=errors,
            )

    async def _run_llm_guided(self, source_url: str, llm_client: LLMClient) -> ComplianceResult:
        steps: list[StepRecord] = []
        screenshots: list[str] = []
        errors: list[str] = []
        form_evidence: list[str] = []
        form_candidates: list[FormCandidate] = []
        primary_form_candidate: FormCandidate | None = None
        llm_form_assessment: dict[str, Any] = {}
        llm_button_candidates: list[dict[str, Any]] = []
        form_found = False

        screenshot_service = ScreenshotService(self.output_dir)
        form_detector = FormDetector()
        navigator = Navigator()
        deadline = time.monotonic() + self.max_runtime_seconds

        async with Crawler(headless=self.headless) as crawler:
            page = await crawler.open(source_url)
            initial_url = page.url

            artifacts = await screenshot_service.capture(page, step_index=0)
            artifact_paths = [artifact.path for artifact in artifacts]
            screenshots.extend(artifact_paths)

            entry_payload = await llm_client.analyze_entry_page(artifacts, current_url=page.url)
            entry_action = self._llm_action(entry_payload)
            llm_button_candidates = self._button_candidates(entry_payload)

            if entry_action == "form_visible":
                form_found = True
                llm_form_assessment = self._form_assessment(entry_payload)
                form_evidence = self._llm_form_evidence(llm_form_assessment)
                detection = await form_detector.detect(page)
                form_candidates = detection.candidates
                primary_form_candidate = detection.primary_candidate
                steps.append(
                    StepRecord(
                        index=0,
                        url=page.url,
                        action="llm_form_visible",
                        reason=self._llm_reason(entry_payload, "LLM found a valid finance form on the initial page."),
                        success=True,
                        screenshots=artifact_paths,
                    )
                )
            elif entry_action == "click_candidates" and llm_button_candidates:
                steps.append(
                    StepRecord(
                        index=0,
                        url=page.url,
                        action="llm_button_candidates",
                        reason=self._llm_reason(
                            entry_payload,
                            "LLM did not find a valid visible finance form and returned candidate buttons.",
                        ),
                        success=True,
                        screenshots=artifact_paths,
                    )
                )

                for candidate_index, candidate in enumerate(llm_button_candidates, start=1):
                    if candidate_index > self.max_steps:
                        errors.append("Navigation stopped because max_steps candidate attempts were reached.")
                        break
                    if time.monotonic() > deadline:
                        errors.append("Navigation stopped because max_runtime was reached.")
                        break

                    if candidate_index > 1:
                        await page.goto(initial_url, wait_until="domcontentloaded")
                        await crawler.wait_for_stable_page(page)

                    target_text = str(candidate.get("text", "")).strip()
                    if not target_text:
                        errors.append("LLM returned a button candidate without visible text.")
                        continue

                    click_result = await navigator.click_best_candidate(page, target_text)
                    steps.append(
                        StepRecord(
                            index=candidate_index,
                            url=page.url,
                            action="click_llm_candidate",
                            target=click_result.text or target_text,
                            reason=str(candidate.get("reason", "")),
                            success=click_result.success,
                            error=click_result.error,
                            screenshots=[],
                        )
                    )
                    if not click_result.success:
                        errors.append(click_result.error or f"Unable to click {target_text!r}.")
                        continue

                    await crawler.wait_for_stable_page(page)
                    validation_artifacts = await screenshot_service.capture(
                        page, step_index=candidate_index
                    )
                    validation_paths = [artifact.path for artifact in validation_artifacts]
                    screenshots.extend(validation_paths)

                    validation_payload = await llm_client.validate_form_page(
                        validation_artifacts, current_url=page.url
                    )
                    validation_action = self._llm_action(validation_payload)
                    if validation_action == "form_visible":
                        form_found = True
                        llm_form_assessment = self._form_assessment(validation_payload)
                        form_evidence = self._llm_form_evidence(llm_form_assessment)
                        detection = await form_detector.detect(page)
                        form_candidates = detection.candidates
                        primary_form_candidate = detection.primary_candidate
                        steps.append(
                            StepRecord(
                                index=candidate_index,
                                url=page.url,
                                action="llm_form_validated",
                                target=target_text,
                                reason=self._llm_reason(
                                    validation_payload,
                                    "LLM validated a finance form after clicking a candidate button.",
                                ),
                                success=True,
                                screenshots=validation_paths,
                            )
                        )
                        break

                    steps.append(
                        StepRecord(
                            index=candidate_index,
                            url=page.url,
                            action="llm_form_rejected",
                            target=target_text,
                            reason=self._llm_reason(
                                validation_payload,
                                "LLM did not validate a finance form on this destination page.",
                            ),
                            success=True,
                            screenshots=validation_paths,
                        )
                    )
            else:
                steps.append(
                    StepRecord(
                        index=0,
                        url=page.url,
                        action="none",
                        reason=self._llm_reason(
                            entry_payload,
                            "LLM did not find a valid finance form or strong candidate buttons.",
                        ),
                        success=True,
                        screenshots=artifact_paths,
                    )
                )

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
                llm_form_assessment=llm_form_assessment,
                llm_button_candidates=llm_button_candidates,
                decision_source="llm_guided_finance_form",
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

    def _llm_action(self, payload: dict[str, Any] | None) -> str:
        if not payload:
            return "none"
        action = str(payload.get("action", "none")).strip().lower()
        if action in {"form_visible", "click_candidates", "none"}:
            return action
        if action == "click":
            return "click_candidates"
        return "none"

    def _button_candidates(self, payload: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not payload:
            return []
        raw_candidates = payload.get("button_candidates") or []
        if not isinstance(raw_candidates, list):
            raw_candidates = []
        if not raw_candidates and payload.get("text"):
            raw_candidates = [
                {
                    "text": payload.get("text"),
                    "reason": payload.get("reason", ""),
                    "confidence": payload.get("confidence", 0.0),
                }
            ]

        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in raw_candidates:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            key = text.lower()
            if not text or key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "text": text,
                    "reason": str(item.get("reason", "")),
                    "confidence": self._float_value(item.get("confidence")),
                }
            )
        candidates.sort(key=lambda item: item["confidence"], reverse=True)
        return candidates[:5]

    def _form_assessment(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        if not payload:
            return {}
        form = payload.get("form")
        if isinstance(form, dict):
            assessment = dict(form)
        else:
            assessment = {}
        assessment.setdefault("reason", str(payload.get("reason", "")))
        assessment.setdefault("confidence", self._float_value(payload.get("confidence")))
        return assessment

    def _llm_form_evidence(self, assessment: dict[str, Any]) -> list[str]:
        evidence: list[str] = []
        for key in (
            "label",
            "purpose",
            "location",
            "submit_text",
            "consent_or_disclosure",
            "why_valid_finance_form",
            "reason",
        ):
            value = assessment.get(key)
            if value:
                evidence.append(str(value))
        visible_fields = assessment.get("visible_fields")
        if isinstance(visible_fields, list):
            evidence.extend(str(item) for item in visible_fields if item)
        return self._dedupe_text(evidence)

    def _llm_reason(self, payload: dict[str, Any] | None, fallback: str) -> str:
        if not payload:
            return fallback
        reason = str(payload.get("reason", "")).strip()
        confidence = self._float_value(payload.get("confidence"))
        if confidence:
            return f"{reason or fallback} Confidence {confidence:.2f}."
        return reason or fallback

    def _float_value(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _dedupe_text(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for value in values:
            normalized = " ".join(str(value).split())
            key = normalized.lower()
            if normalized and key not in seen:
                seen.add(key)
                output.append(normalized)
        return output
