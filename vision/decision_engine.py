from __future__ import annotations

import logging

from playwright.async_api import Page

from core.models import NavigationDecision, ScreenshotArtifact
from detectors.element_matcher import ElementMatcher
from vision.llm_client import LLMClient


logger = logging.getLogger(__name__)


class DecisionEngine:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client
        self.matcher = ElementMatcher()

    async def decide(
        self,
        page: Page,
        screenshots: list[ScreenshotArtifact],
        current_url: str,
    ) -> NavigationDecision:
        if self.llm_client and self.llm_client.enabled:
            try:
                payload = await self.llm_client.decide(screenshots, current_url=current_url)
                decision = self._coerce_decision(payload)
                if decision:
                    return decision
            except Exception as exc:
                logger.warning("LLM decision failed; falling back to heuristics: %s", exc)

        return await self._heuristic_decision(page)

    def _coerce_decision(self, payload: dict | None) -> NavigationDecision | None:
        if not payload:
            return None
        action = str(payload.get("action", "none")).strip().lower()
        if action not in {"form_visible", "click", "none"}:
            return None
        confidence = payload.get("confidence", 0.0)
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            confidence_value = 0.0
        return NavigationDecision(
            action=action,
            text=payload.get("text"),
            reason=str(payload.get("reason", "")),
            confidence=confidence_value,
            raw=payload,
        )

    async def _heuristic_decision(self, page: Page) -> NavigationDecision:
        candidates = await self.matcher.find_click_candidates(page)
        if candidates:
            best = candidates[0]
            return NavigationDecision(
                action="click",
                text=best.text,
                reason=f"Heuristic CTA match: {best.text}",
                confidence=min(best.score / 150, 1.0),
            )
        return NavigationDecision(
            action="none",
            reason="No form was detected and no CTA candidate was found.",
            confidence=0.0,
        )
