from __future__ import annotations

from urllib.parse import urlparse


def ensure_url_scheme(url: str) -> str:
    candidate = url.strip()
    if not urlparse(candidate).scheme:
        return f"https://{candidate}"
    return candidate
