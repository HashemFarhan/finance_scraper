from __future__ import annotations

from urllib.parse import urldefrag, urlparse, urlunparse


def ensure_url_scheme(url: str) -> str:
    candidate = url.strip()
    if not urlparse(candidate).scheme:
        return f"https://{candidate}"
    return candidate


def normalize_url(url: str) -> str:
    parsed, _fragment = urldefrag(url)
    parts = urlparse(parsed)
    netloc = parts.netloc.lower()
    scheme = parts.scheme.lower()
    path = parts.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", parts.query, ""))
