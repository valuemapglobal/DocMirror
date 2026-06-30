# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
OpenAI Backend — GPT-4o vision connector.

Wraps the OpenAI Python SDK to provide vision-based document analysis
through the unified ``AIBackend`` protocol.

Usage::

    from docmirror.input.adapters.ai.config import AIConfig
    from docmirror.input.adapters.ai.backends.openai import OpenAIBackend

    backend = OpenAIBackend(AIConfig(openai_api_key="sk-..."))
    result = await backend.analyze_page(page_image_bytes)
"""

from __future__ import annotations

import base64
import importlib.util
import logging
from typing import Any

from docmirror.input.adapters.ai.config import (
    BASE_RETRY_DELAY_MS,
    MAX_RETRIES,
    AIConfig,
)
from docmirror.input.adapters.ai.protocol import AIAnalysisResult, AIBackendCapabilities

logger = logging.getLogger(__name__)


class OpenAIBackend:
    """OpenAI GPT-4o vision backend for document analysis."""

    def __init__(self, config: AIConfig):
        self._config = config
        self._client = None
        self._capabilities = AIBackendCapabilities(
            vision=True,
            chart_description=True,
            table_extraction=True,
            formula_extraction=True,
            page_understanding=True,
            max_image_size_mb=20.0,
            supported_tasks={"describe", "analyze", "extract"},
        )

    @property
    def name(self) -> str:
        return "openai"

    @property
    def capabilities(self) -> AIBackendCapabilities:
        return self._capabilities

    @property
    def is_available(self) -> bool:
        if not self._config.openai_api_key:
            return False
        return importlib.util.find_spec("openai") is not None

    def _get_client(self):
        """Lazy-initialize the OpenAI client."""
        if self._client is not None:
            return self._client
        try:
            from openai import AsyncOpenAI

            kwargs = {"api_key": self._config.openai_api_key}
            if self._config.openai_base_url:
                kwargs["base_url"] = self._config.openai_base_url
            self._client = AsyncOpenAI(**kwargs)
            return self._client
        except ImportError:
            raise ImportError("openai package not installed. Install with: pip install openai")

    async def analyze_page(
        self,
        image_bytes: bytes,
        *,
        options: dict[str, Any] | None = None,
    ) -> AIAnalysisResult:
        """Analyze a page image using GPT-4o vision.

        Args:
            image_bytes: PNG or JPEG bytes of the page image.
            options: See ``AIBackend.analyze_page`` for common options.

        Returns:
            Structured analysis result.
        """
        opts = options or {}
        task = opts.get("task", "analyze")
        model = opts.get("model", self._config.openai_model)
        language = opts.get("language", "")

        url = self._image_to_data_url(image_bytes)

        if task == "describe":
            system_prompt = "Describe the content of this document page concisely."
        elif task == "extract":
            system_prompt = (
                "Extract all structured data from this page. "
                "Return JSON with 'tables', 'key_values', and 'text' fields."
            )
        else:
            system_prompt = (
                "Analyze this document page thoroughly. "
                "Return JSON with: "
                "'page_description' (str), "
                "'tables' (list of {headers, rows}), "
                "'charts' (dict of region_id -> description), "
                "'formulas' (list of LaTeX strings), "
                "'text' (full extracted text in reading order)."
            )

        if language:
            system_prompt += f"\nThe document language is: {language}."

        client = self._get_client()
        response = await self._call_with_retry(
            client,
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": url, "detail": "high"},
                        },
                    ],
                },
            ],
            max_tokens=self._config.openai_max_tokens,
            temperature=self._config.openai_temperature,
        )

        return self._parse_response(response, task)

    async def describe_image(
        self,
        image_bytes: bytes,
        *,
        context: str = "",
        options: dict[str, Any] | None = None,
    ) -> str:
        """Generate a description of a chart/image for accessibility.

        Args:
            image_bytes: Image bytes (PNG/JPEG).
            context: Context hint (``"chart"``, ``"photo"``, ``"diagram"``).
            options: Backend-specific options.

        Returns:
            Natural language description suitable for alt-text.
        """
        opts = options or {}
        model = opts.get("model", self._config.openai_model)
        url = self._image_to_data_url(image_bytes)

        context_prompt = ""
        if context == "chart":
            context_prompt = "This is a chart or graph. Describe its type, axes, data trends, and key values in detail."
        elif context == "diagram":
            context_prompt = (
                "This is a diagram or illustration. Describe its components, relationships, and overall meaning."
            )
        elif context == "photo":
            context_prompt = "Describe this photograph in detail."
        else:
            context_prompt = "Describe this image in detail for accessibility purposes."

        client = self._get_client()
        response = await self._call_with_retry(
            client,
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an accessibility alt-text generator. Describe images concisely but thoroughly.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": context_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": url, "detail": "high"},
                        },
                    ],
                },
            ],
            max_tokens=self._config.openai_max_tokens,
            temperature=self._config.openai_temperature,
        )
        return self._extract_text(response)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _image_to_data_url(self, image_bytes: bytes) -> str:
        """Convert image bytes to a base64 data URL for the API."""
        import imghdr

        img_type = imghdr.what(None, h=image_bytes) or "png"
        b64 = base64.b64encode(image_bytes).decode("ascii")
        return f"data:image/{img_type};base64,{b64}"

    async def _call_with_retry(self, client, **kwargs) -> Any:
        """Call OpenAI API with retry logic."""
        import asyncio

        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.chat.completions.create(**kwargs)
                return response
            except Exception as exc:
                logger.warning(
                    "OpenAI API call failed (attempt %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    exc,
                )
                last_exc = exc
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(BASE_RETRY_DELAY_MS * (2**attempt) / 1000)
        raise last_exc  # type: ignore[misc]

    def _parse_response(self, response: Any, task: str) -> AIAnalysisResult:
        """Parse OpenAI API response into ``AIAnalysisResult``."""
        text = self._extract_text(response)

        # Try JSON extraction first

        json_data = self._try_extract_json(text)
        if json_data and task == "analyze":
            return AIAnalysisResult(
                page_description=json_data.get("page_description", ""),
                tables=json_data.get("tables", []),
                chart_descriptions=json_data.get("charts", {}),
                formulas=json_data.get("formulas", []),
                text_overlay=json_data.get("text", text),
                confidence=0.85,
                raw_response={},
                usage=self._extract_usage(response),
            )

        return AIAnalysisResult(
            page_description=text if task in ("describe", "analyze") else "",
            text_overlay=text,
            confidence=0.80,
            raw_response={},
            usage=self._extract_usage(response),
        )

    def _extract_text(self, response: Any) -> str:
        """Extract text content from an OpenAI chat completion response."""
        try:
            return response.choices[0].message.content or ""
        except (AttributeError, IndexError, TypeError):
            return ""

    def _extract_usage(self, response: Any) -> dict[str, int]:
        """Extract token usage from API response."""
        try:
            usage = response.usage
            return {
                "prompt_tokens": usage.prompt_tokens or 0,
                "completion_tokens": usage.completion_tokens or 0,
                "total_tokens": usage.total_tokens or 0,
            }
        except (AttributeError, TypeError):
            return {}

    @staticmethod
    def _try_extract_json(text: str) -> dict[str, Any] | None:
        """Try to parse a JSON object from the response text.

        Handles both pure JSON responses and code-block-wrapped JSON.
        """
        import json

        # Try parsing directly
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # Try extracting from code block
        import re

        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(1))
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

        return None


__all__ = ["OpenAIBackend"]
