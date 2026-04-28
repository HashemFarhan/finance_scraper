from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page


def clean_text(text: str, max_chars: int | None = None) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = normalized.strip()
    if max_chars is not None:
        return normalized[:max_chars]
    return normalized


async def extract_visible_text(page: Page, max_chars: int | None = None) -> str:
    text = await page.evaluate("() => document.body ? document.body.innerText : ''")
    return clean_text(text or "", max_chars=max_chars)
