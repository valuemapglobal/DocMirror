# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Gemini Backend — Google Gemini 2.0/2.5 vision connector.

Wraps the Google Generative AI Python SDK to provide vision-based
document analysis through the unified ``AIBackend`` protocol.

Usage::

    from docmirror.input.adapters.ai.config import AIConfig
    from docmirror.input.adapters.ai.backends.gemini import GeminiBackend

    backend = GeminiBackend(AIConfig(gemini_api_key="AIza..."))
    result = await backend.analyze_page(page_image_bytes)
"""

from __future__ import annotations

import logging
from typing import Any

from docmirror.input.adapters.ai.config import (
    BASE_RETRY_DELAY_MS,
    MAX_RETRIES,
    AIConfig,
)
from docmirror.input.adapters.ai.protocol import AIAnalysisResult, AIBackendCapabilities

logger = logging.getLogger(__name__)


class GeminiBackend:
    """Google Gemini vision backend for document analysis."""

    def __init__(self, config: AIConfig):
        self._config = config
        self._model = None
        self._capabilities = AIBackendCapabilities(
            vision=True,
            chart_description=True,
            table_extraction=False,
            formula_extraction=True,
            page_understanding=True,
            max_image_size_mb=20.0,
            supported_tasks={"describe", "analyze", "extract"},
        )

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def capabilities(self) -> AIBackendCapabilities:
        return self._capabilities

    @property
    def is_available(self) -> bool:
        if not self._config.gemini_api_key:
            return False
        try:
            import google.generativeai as genai  # noqa: F401

            return True
        except ImportError:
            return False

    def _get_model(self):
        """Lazy-initialize the Gemini model."""
        if self._model is not None:
            return self._model
        try:
            import google.generativeai as genai

            genai.configure(api_key=self._config.gemini_api_key)
            self._model = genai.GenerativeModel(
                model_name=self._config.gemini_model,
                generation_config={
                    "max_output_tokens": self._config.gemini_max_tokens,
                    "temperature": self._config.gemini_temperature,
                },
            )
            return self._model
        except ImportError:
            raise ImportError(
                "google-generativeai package not installed. Install with: pip install google-generativeai"
            )

    async def analyze_page(
        self,
        image_bytes: bytes,
        *,
        options: dict[str, Any] | None = None,
    ) -> AIAnalysisResult:
        """Analyze a page image using Gemini vision."""
        opts = options or {}
        task = opts.get("task", "analyze")
        language = opts.get("language", "")

        if task == "describe":
            prompt = "Describe the content of this document page concisely."
        elif task == "extract":
            prompt = (
                "Extract all structured data from this page. "
                "Return JSON with 'tables', 'key_values', and 'text' fields."
            )
        else:
            prompt = (
                "Analyze this document page thoroughly. "
                "Return JSON with: "
                "'page_description' (str), "
                "'tables' (list of {headers, rows}), "
                "'charts' (dict of region_id -> description), "
                "'formulas' (list of LaTeX strings), "
                "'text' (full extracted text in reading order)."
            )

        if language:
            prompt += f"\\nThe document language is: {language}."

        model = self._get_model()
        response = await self._call_with_retry(
            model,
            prompt=prompt,
            image_bytes=image_bytes,
        )

        return self._parse_response(response, task)

    async def describe_image(
        self,
        image_bytes: bytes,
        *,
        context: str = "",
        options: dict[str, Any] | None = None,
    ) -> str:
        """Generate a description of a chart/image for accessibility."""
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

        system_context = "You are an accessibility alt-text generator. Describe images concisely but thoroughly."

        model = self._get_model()
        response = await self._call_with_retry(
            model,
            prompt=f"{system_context}\\n\\n{context_prompt}",
            image_bytes=image_bytes,
        )
        return response.text if hasattr(response, "text") else str(response)

    async def _call_with_retry(self, model, *, prompt: str, image_bytes: bytes) -> Any:
        """Call Gemini API with retry logic."""
        import asyncio

        import google.generativeai as genai

        image_part = genai.upload_file(
            io_bytes=image_bytes,
            display_name="page_image",
        )

        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                response = await model.generate_content_async([prompt, image_part])
                return response
            except Exception as exc:
                logger.warning(
                    "Gemini API call failed (attempt %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    exc,
                )
                last_exc = exc
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(BASE_RETRY_DELAY_MS * (2**attempt) / 1000)
        raise last_exc  # type: ignore[misc]

    def _parse_response(self, response: Any, task: str) -> AIAnalysisResult:
        """Parse Gemini API response into ``AIAnalysisResult``."""
        text = response.text if hasattr(response, "text") else str(response)

        json_data = self._try_extract_json(text)
        if json_data and task == "analyze":
            return AIAnalysisResult(
                page_description=json_data.get("page_description", ""),
                tables=json_data.get("tables", []),
                chart_descriptions=json_data.get("charts", {}),
                formulas=json_data.get("formulas", []),
                text_overlay=json_data.get("text", text),
                confidence=0.82,
                raw_response={},
            )

        return AIAnalysisResult(
            page_description=text if task in ("describe", "analyze") else "",
            text_overlay=text,
            confidence=0.75,
            raw_response={},
        )

    @staticmethod
    def _try_extract_json(text: str) -> dict[str, Any] | None:
        """Try to parse a JSON object from the response text."""
        import json
        import re

        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(1))
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

        return None


__all__ = ["GeminiBackend"]
