from __future__ import annotations

from playwright.async_api import BrowserContext
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from core.models import PolicyDocument
from extractors.text_extractor import extract_visible_text


class PolicyExtractor:
    def __init__(self, context: BrowserContext, timeout_ms: int = 30_000, max_chars: int = 200_000) -> None:
        self.context = context
        self.timeout_ms = timeout_ms
        self.max_chars = max_chars

    async def extract(self, url: str | None) -> PolicyDocument:
        if not url:
            return PolicyDocument(url=None)

        page = await self.context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            try:
                await page.wait_for_load_state("networkidle", timeout=8_000)
            except PlaywrightTimeoutError:
                pass
            text = await extract_visible_text(page, max_chars=self.max_chars)
            return PolicyDocument(url=url, text=text)
        except Exception as exc:
            return PolicyDocument(url=url, error=f"Could not extract policy text from {url}: {exc}")
        finally:
            await page.close()
