from __future__ import annotations

from dataclasses import dataclass

from playwright.async_api import Page


CTA_WEIGHTS = {
    "get started": 100,
    "start": 92,
    "apply now": 92,
    "continue": 90,
    "next": 88,
    "sign up": 86,
    "register": 86,
    "request": 82,
    "quote": 80,
    "contact": 78,
    "join": 76,
    "enroll": 76,
    "book": 72,
    "submit": 70,
}


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
        requested = (requested_text or "").strip().lower()
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
        lowered = text.lower()
        score = 0
        if requested:
            if lowered == requested:
                score += 150
            elif requested in lowered or lowered in requested:
                score += 115

        for phrase, weight in CTA_WEIGHTS.items():
            if phrase == lowered:
                score += weight
            elif phrase in lowered:
                score += weight - 15
        return score

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
