from __future__ import annotations

from dataclasses import dataclass

from playwright.async_api import Page


@dataclass
class ElementCandidate:
    text: str
    tag: str
    href: str | None
    score: int


class ElementMatcher:
    async def find_click_candidates(
        self, page: Page, requested_text: str | None = None
    ) -> list[ElementCandidate]:
        requested = self._normalize(requested_text)
        if not requested:
            return []

        elements = await page.evaluate(
            r"""
            () => {
              const normalize = value => (value || '').replace(/\s+/g, ' ').trim();
              const isVisible = el => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 &&
                  style.visibility !== 'hidden' && style.display !== 'none';
              };
              return Array.from(document.querySelectorAll('a,button,input[type="button"],input[type="submit"],[role="button"]'))
                .filter(isVisible)
                .map(el => ({
                  text: normalize(el.innerText || el.value || el.getAttribute('aria-label') || el.title),
                  tag: el.tagName.toLowerCase(),
                  href: el.href || null
                }))
                .filter(item => item.text);
            }
            """
        )
        candidates: list[ElementCandidate] = []
        for element in elements:
            text = str(element.get("text", ""))
            score = self._score(text, requested)
            if score <= 0:
                continue
            candidates.append(
                ElementCandidate(
                    text=text,
                    tag=str(element.get("tag", "")),
                    href=element.get("href"),
                    score=score,
                )
            )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return self._dedupe(candidates)

    def _score(self, text: str, requested: str) -> int:
        lowered = self._normalize(text)
        if lowered == requested:
            return 150
        if requested in lowered:
            return 115
        if lowered in requested:
            return 90
        return 0

    def _dedupe(self, candidates: list[ElementCandidate]) -> list[ElementCandidate]:
        seen: set[str] = set()
        output: list[ElementCandidate] = []
        for candidate in candidates:
            key = candidate.text.lower()
            if key in seen:
                continue
            seen.add(key)
            output.append(candidate)
        return output

    def _normalize(self, value: str | None) -> str:
        return " ".join((value or "").split()).lower()
