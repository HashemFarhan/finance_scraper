from __future__ import annotations

import logging
import re

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from core.models import ClickResult
from detectors.element_matcher import ElementMatcher


logger = logging.getLogger(__name__)


class Navigator:
    def __init__(self, click_timeout_ms: int = 5_000) -> None:
        self.click_timeout_ms = click_timeout_ms
        self.matcher = ElementMatcher()

    async def click_best_candidate(self, page: Page, requested_text: str) -> ClickResult:
        attempted: list[str] = []
        texts = [requested_text]
        candidates = await self.matcher.find_click_candidates(page, requested_text=requested_text)
        texts.extend(candidate.text for candidate in candidates if candidate.text)

        for text in self._unique(texts):
            attempted.append(text)
            result = await self._click_by_accessible_text(page, text)
            if result.success:
                return result

        js_result = await self._click_by_dom_text(page, requested_text)
        if js_result.success:
            return js_result

        return ClickResult(
            success=False,
            text=requested_text,
            error=f"Could not click requested text. Attempted: {', '.join(attempted[:6])}",
        )

    async def _click_by_accessible_text(self, page: Page, text: str) -> ClickResult:
        escaped = re.escape(text.strip())
        if not escaped:
            return ClickResult(success=False, text=text, error="Empty click target.")

        patterns = [
            re.compile(rf"^\s*{escaped}\s*$", re.IGNORECASE),
            re.compile(escaped, re.IGNORECASE),
        ]
        locator_factories = [
            lambda pattern: page.get_by_role("button", name=pattern),
            lambda pattern: page.get_by_role("link", name=pattern),
            lambda pattern: page.get_by_text(pattern),
        ]

        for pattern in patterns:
            for factory in locator_factories:
                locator = factory(pattern)
                try:
                    count = await locator.count()
                    for index in range(min(count, 5)):
                        candidate = locator.nth(index)
                        if not await candidate.is_visible():
                            continue
                        await candidate.click(timeout=self.click_timeout_ms)
                        return ClickResult(success=True, text=text, method="accessible_text")
                except PlaywrightTimeoutError as exc:
                    logger.debug("Click timed out for %s: %s", text, exc)
                except Exception as exc:
                    logger.debug("Click failed for %s: %s", text, exc)

        return ClickResult(success=False, text=text, error=f"No visible locator matched {text!r}.")

    async def _click_by_dom_text(self, page: Page, text: str) -> ClickResult:
        clicked = await page.evaluate(
            r"""
            (wanted) => {
              const normalize = value => (value || '').replace(/\s+/g, ' ').trim().toLowerCase();
              const target = normalize(wanted);
              if (!target) return false;
              const nodes = Array.from(document.querySelectorAll('a,button,input,[role="button"]'));
              const isVisible = el => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 &&
                  style.visibility !== 'hidden' && style.display !== 'none';
              };
              for (const el of nodes) {
                const text = normalize(el.innerText || el.value || el.getAttribute('aria-label'));
                if (isVisible(el) && (text === target || text.includes(target) || target.includes(text))) {
                  el.click();
                  return text || true;
                }
              }
              return false;
            }
            """,
            text,
        )
        if clicked:
            return ClickResult(success=True, text=str(clicked), method="dom_text")
        return ClickResult(success=False, text=text, error=f"DOM click fallback did not match {text!r}.")

    def _unique(self, values: list[str | None]) -> list[str]:
        seen: set[str] = set()
        unique_values: list[str] = []
        for value in values:
            normalized = " ".join((value or "").split())
            key = normalized.lower()
            if normalized and key not in seen:
                seen.add(key)
                unique_values.append(normalized)
        return unique_values
