from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

from core.models import ConsentExtraction
from extractors.text_extractor import extract_visible_text


KEYWORD_GROUPS = (
    ("by clicking",),
    ("agree", "terms"),
    ("agree", "privacy"),
    ("consent",),
    ("terms", "privacy"),
    ("terms and conditions",),
    ("privacy policy",),
    ("authorize",),
    ("sms",),
    ("text message",),
)


class ConsentExtractor:
    async def extract(self, page: Page) -> ConsentExtraction:
        text = await extract_visible_text(page)
        evidence = extract_consent_lines(text)
        return ConsentExtraction(
            submit_language=evidence[0] if evidence else None,
            evidence=evidence,
        )


def extract_consent_lines(text: str, max_lines: int = 8) -> list[str]:
    lines = [_normalize(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    candidates: list[str] = []
    for line in lines:
        if not _is_consent_line(line):
            continue
        sentence_matches = [
            sentence for sentence in _split_sentences(line) if _is_consent_line(sentence)
        ]
        candidates.extend(sentence_matches or [line])

    if not candidates:
        sentences = _split_sentences(_normalize(text))
        candidates = [sentence for sentence in sentences if _is_consent_line(sentence)]

    return _dedupe(candidates)[:max_lines]


def _is_consent_line(line: str) -> bool:
    lowered = line.lower()
    if len(lowered) > 900:
        return False
    return any(all(keyword in lowered for keyword in group) for group in KEYWORD_GROUPS)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _split_sentences(value: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", value) if sentence.strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output
