from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import os
import re
from pathlib import Path

from core.models import ScreenshotArtifact


ENTRY_FORM_PROMPT = """You are a finance-form inspection engine.
Return only JSON.

Goal:
Find a valid finance-related consumer form, such as a loan, cash advance, personal loan,
credit, quote, prequalification, application, debt, insurance, banking, or other finance
lead form. Do not treat search, newsletter, login, cookie, contact-only footer, privacy
request, or generic navigation widgets as the target form.

On the first page only, choose one of:
{
  "action": "form_visible",
  "reason": "...",
  "confidence": 0.0,
  "form": {
    "label": "...",
    "purpose": "...",
    "location": "...",
    "visible_fields": ["..."],
    "submit_text": "...",
    "consent_or_disclosure": "...",
    "why_valid_finance_form": "..."
  }
}
{
  "action": "click_candidates",
  "reason": "...",
  "confidence": 0.0,
  "button_candidates": [
    {
      "text": "exact visible button or link text",
      "reason": "why this likely leads to a finance form",
      "confidence": 0.0
    }
  ]
}
{
  "action": "none",
  "reason": "...",
  "confidence": 0.0,
  "button_candidates": []
}

If a valid finance form is visible, choose form_visible and return details of that form.
If no valid finance form is visible, return up to five strong visible button/link candidates
that are likely to lead to that finance form. Prefer exact visible text.
"""


FORM_VALIDATION_PROMPT = """You are a finance-form validation engine.
Return only JSON.

Goal:
Evaluate whether the current page shows a valid finance-related consumer form, such as a
loan, cash advance, personal loan, credit, quote, prequalification, application, debt,
insurance, banking, or other finance lead form.

Do not look for new navigation buttons. Do not suggest clicks. Only validate whether the
form is visible on this page.

Return one of:
{
  "action": "form_visible",
  "reason": "...",
  "confidence": 0.0,
  "form": {
    "label": "...",
    "purpose": "...",
    "location": "...",
    "visible_fields": ["..."],
    "submit_text": "...",
    "consent_or_disclosure": "...",
    "why_valid_finance_form": "..."
  }
}
{
  "action": "none",
  "reason": "...",
  "confidence": 0.0
}
"""


SYSTEM_PROMPT = ENTRY_FORM_PROMPT


class LLMClient:
    def __init__(self, model: str | None = None, max_images: int = 4, timeout: float = 60.0) -> None:
        local_model = _local_setting("OPENAI_MODEL")
        self.model = model or os.getenv("OPENAI_MODEL") or local_model or "gpt-4o-mini"
        self.max_images = max_images
        self.timeout = timeout
        self.api_key = os.getenv("OPENAI_API_KEY") or _local_setting("OPENAI_API_KEY")
        self._client = None
        if self.api_key:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key, timeout=timeout)
            except ImportError:
                self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def decide(
        self,
        screenshots: list[ScreenshotArtifact],
        current_url: str,
    ) -> dict | None:
        return await self.analyze_entry_page(screenshots, current_url)

    async def analyze_entry_page(
        self,
        screenshots: list[ScreenshotArtifact],
        current_url: str,
    ) -> dict | None:
        if not self.enabled:
            return None
        return await asyncio.to_thread(
            self._decide_sync,
            screenshots,
            current_url,
            ENTRY_FORM_PROMPT,
            "Inspect the initial page screenshots. Decide whether a valid finance form is visible or return strong button candidates that may lead to it.",
        )

    async def validate_form_page(
        self,
        screenshots: list[ScreenshotArtifact],
        current_url: str,
    ) -> dict | None:
        if not self.enabled:
            return None
        return await asyncio.to_thread(
            self._decide_sync,
            screenshots,
            current_url,
            FORM_VALIDATION_PROMPT,
            "Inspect this navigated page. Validate whether a valid finance form is visible. Do not suggest new buttons.",
        )

    def _decide_sync(
        self,
        screenshots: list[ScreenshotArtifact],
        current_url: str,
        system_prompt: str,
        instruction: str,
    ) -> dict | None:
        prompt = (
            f"Current URL: {current_url}\n"
            f"{instruction}\n"
            "Inspect the screenshots in order. Return only JSON."
        )
        image_urls = [self._data_url(Path(item.path)) for item in screenshots[: self.max_images]]

        response_text = self._call_responses_api(system_prompt, prompt, image_urls)
        if response_text is None:
            response_text = self._call_chat_completions(system_prompt, prompt, image_urls)
        return parse_json_response(response_text)

    def _call_responses_api(
        self, system_prompt: str, prompt: str, image_urls: list[str]
    ) -> str | None:
        if not hasattr(self._client, "responses"):
            return None
        content = [{"type": "input_text", "text": prompt}]
        content.extend({"type": "input_image", "image_url": image_url} for image_url in image_urls)
        response = self._client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": content},
            ],
            temperature=0,
        )
        return getattr(response, "output_text", None)

    def _call_chat_completions(self, system_prompt: str, prompt: str, image_urls: list[str]) -> str:
        content = [{"type": "text", "text": prompt}]
        content.extend(
            {"type": "image_url", "image_url": {"url": image_url}} for image_url in image_urls
        )
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
        except Exception:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content},
                ],
                temperature=0,
            )
        return response.choices[0].message.content

    def _data_url(self, path: Path) -> str:
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"


def _local_setting(name: str) -> str | None:
    try:
        from config import local_settings
    except Exception:
        return None
    value = getattr(local_settings, name, None)
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def parse_json_response(text: str | None) -> dict | None:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
