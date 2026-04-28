from __future__ import annotations

from playwright.async_api import Page

from core.models import PolicyLinks


class LinkExtractor:
    async def extract(self, page: Page) -> PolicyLinks:
        anchors = await page.evaluate(
            r"""
            () => Array.from(document.querySelectorAll('a[href]')).map(anchor => ({
              text: (anchor.innerText || anchor.getAttribute('aria-label') || anchor.title || '').replace(/\s+/g, ' ').trim(),
              href: anchor.href
            }))
            """
        )
        terms = self._best_link(anchors, ("terms", "conditions", "terms of use"))
        privacy = self._best_link(anchors, ("privacy", "privacy policy"))
        evidence = []
        for link in (terms, privacy):
            if link:
                evidence.append({"text": link.get("text", ""), "href": link.get("href", "")})
        return PolicyLinks(
            terms_url=terms.get("href") if terms else None,
            privacy_url=privacy.get("href") if privacy else None,
            evidence=evidence,
        )

    def _best_link(
        self, anchors: list[dict[str, str]], keywords: tuple[str, ...]
    ) -> dict[str, str] | None:
        scored = []
        for anchor in anchors:
            text = str(anchor.get("text", ""))
            href = str(anchor.get("href", ""))
            score = 0
            for keyword in keywords:
                if keyword in text.lower():
                    score += 100
                if keyword.replace(" ", "-") in href.lower() or keyword in href.lower():
                    score += 60
            if score:
                scored.append((score, anchor))
        if not scored:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]
