from __future__ import annotations

from datetime import datetime
from pathlib import Path

from playwright.async_api import Page

from core.models import ScreenshotArtifact


class ScreenshotService:
    def __init__(self, output_dir: Path | str = "runs", max_segments: int = 6) -> None:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self.run_dir = Path(output_dir) / "screenshots" / timestamp
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.max_segments = max_segments

    async def capture(self, page: Page, step_index: int) -> list[ScreenshotArtifact]:
        artifacts: list[ScreenshotArtifact] = []
        full_path = self.run_dir / f"step_{step_index:02d}_full.png"
        await page.screenshot(path=str(full_path), full_page=True)
        artifacts.append(
            ScreenshotArtifact(
                path=str(full_path.resolve()),
                kind="full_page",
                index=0,
                url=page.url,
            )
        )

        metrics = await page.evaluate(
            """
            () => ({
              height: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight),
              viewport: window.innerHeight,
              currentY: window.scrollY
            })
            """
        )
        height = int(metrics.get("height", 0))
        viewport = max(int(metrics.get("viewport", 768)), 1)
        original_y = int(metrics.get("currentY", 0))
        positions = list(range(0, min(height, viewport * self.max_segments), viewport))

        for index, scroll_y in enumerate(positions):
            await page.evaluate("(y) => window.scrollTo(0, y)", scroll_y)
            await page.wait_for_timeout(150)
            segment_path = self.run_dir / f"step_{step_index:02d}_scroll_{index:02d}.png"
            await page.screenshot(path=str(segment_path), full_page=False)
            artifacts.append(
                ScreenshotArtifact(
                    path=str(segment_path.resolve()),
                    kind="scroll_segment",
                    index=index,
                    url=page.url,
                    scroll_y=scroll_y,
                )
            )

        await page.evaluate("(y) => window.scrollTo(0, y)", original_y)
        return artifacts
