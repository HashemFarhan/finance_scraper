from __future__ import annotations

import logging

from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError


logger = logging.getLogger(__name__)


class Crawler:
    def __init__(
        self,
        headless: bool = True,
        timeout_ms: int = 30_000,
        viewport: dict[str, int] | None = None,
    ) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.viewport = viewport or {"width": 1365, "height": 768}
        self._playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None

    async def __aenter__(self) -> "Crawler":
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context(viewport=self.viewport)
        self.context.set_default_timeout(self.timeout_ms)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def open(self, url: str) -> Page:
        if not self.context:
            raise RuntimeError("Crawler context has not been initialized.")
        page = await self.context.new_page()
        page.set_default_timeout(self.timeout_ms)
        await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        await self.wait_for_stable_page(page)
        return page

    async def wait_for_stable_page(self, page: Page, timeout_ms: int = 10_000) -> None:
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            logger.debug("Timed out waiting for networkidle; continuing with current page state.")
        await page.wait_for_timeout(300)
