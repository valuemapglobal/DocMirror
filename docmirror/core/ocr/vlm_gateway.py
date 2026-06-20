# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""VLM (Vision-Language Model) OCR gateway routing.

Coordinates base64 image encoding and dispatches layout and text parsing
to the configured external VLM provider.
"""

from __future__ import annotations

import base64
import logging
from abc import ABC, abstractmethod
from typing import Any

from docmirror.configs.runtime.settings import default_settings

logger = logging.getLogger(__name__)


class BaseVlmClient(ABC):
    """Abstract base class for Multimodal VLM API clients."""

    @abstractmethod
    def call_api(self, image_base64: str, config: Any) -> str | None:
        """Call the VLM API with base64 encoded image and return text response."""
        pass


class OpenAiVlmClient(BaseVlmClient):
    """Client for OpenAI Chat Completions API and compatible endpoints."""

    def call_api(self, image_base64: str, config: Any) -> str | None:
        import requests

        url = config.api_base or "https://api.openai.com/v1/chat/completions"
        if config.api_base and not url.endswith("/chat/completions") and not url.endswith("/chat/completions/"):
            url = url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.api_key or ''}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config.model,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": config.prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                    ],
                }
            ],
        }
        response = requests.post(url, json=payload, headers=headers, timeout=config.timeout)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class GeminiVlmClient(BaseVlmClient):
    """Client for Google Gemini Developer API."""

    def call_api(self, image_base64: str, config: Any) -> str | None:
        import requests

        url = (
            config.api_base or f"https://generativelanguage.googleapis.com/v1beta/models/{config.model}:generateContent"
        )
        headers = {"Content-Type": "application/json"}
        params = {}
        if not config.api_base:
            params["key"] = config.api_key or ""
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": config.prompt},
                        {"inlineData": {"mimeType": "image/jpeg", "data": image_base64}},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": config.temperature,
                "maxOutputTokens": config.max_tokens,
            },
        }
        response = requests.post(url, json=payload, headers=headers, params=params, timeout=config.timeout)
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]


class AnthropicVlmClient(BaseVlmClient):
    """Client for Anthropic Claude messages API."""

    def call_api(self, image_base64: str, config: Any) -> str | None:
        import requests

        url = config.api_base or "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": config.api_key or "",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_base64,
                            },
                        },
                        {"type": "text", "text": config.prompt},
                    ],
                }
            ],
        }
        response = requests.post(url, json=payload, headers=headers, timeout=config.timeout)
        response.raise_for_status()
        return response.json()["content"][0]["text"]


class VlmOcrGateway:
    """Gateway router dispatching page image OCR parser requests to VLMs."""

    def __init__(self) -> None:
        openai_compatible = OpenAiVlmClient()
        anthropic = AnthropicVlmClient()
        self._clients: dict[str, BaseVlmClient] = {
            "openai": openai_compatible,
            "azure": openai_compatible,
            "dashscope": openai_compatible,
            "qwen": openai_compatible,
            "gemini": GeminiVlmClient(),
            "anthropic": anthropic,
            "claude": anthropic,
        }

    def process_image(self, img_bgr: Any, page_idx: int) -> dict[str, Any] | None:
        """Transcode image and dispatch to configured VLM client."""
        cfg = default_settings.vlm
        provider_name = cfg.provider.lower().strip()
        client = self._clients.get(provider_name)
        if not client:
            logger.warning(f"[VlmGateway] Unsupported VLM provider: {cfg.provider}")
            return None

        # API key verification (skip check if api_base is set, e.g. for custom proxies/local gateways)
        if not cfg.api_key and not cfg.api_base:
            logger.warning(f"[VlmGateway] api_key not configured for provider: {cfg.provider}")
            return None

        # Encode image
        import cv2

        success, buf = cv2.imencode(".jpg", img_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not success:
            logger.warning(f"[VlmGateway] OpenCV failed to encode page {page_idx} to JPEG")
            return None
        img_base64 = base64.b64encode(buf.tobytes()).decode("ascii")

        try:
            logger.info(
                f"[VlmGateway] Dispatching page {page_idx} to VLM (provider={provider_name}, model={cfg.model})"
            )
            text_out = client.call_api(img_base64, cfg)
            if not text_out:
                return None

            h, w = img_bgr.shape[:2]
            return {
                "content_type": "general",
                "lines": [{"text": text_out, "bbox": (0, 0, w, h)}],
                "page_h": h,
                "page_w": w,
            }
        except Exception as e:
            logger.error(f"[VlmGateway] Failed to recognize page {page_idx} via VLM API: {e}", exc_info=True)
            return None


_gateway = VlmOcrGateway()


def vlm_ocr_provider(img_bgr: Any, page_idx: int = 0, **_kwargs: Any) -> dict[str, Any] | None:
    """Unified callback target configured in DOCMIRROR_EXTERNAL_OCR_PROVIDER."""
    return _gateway.process_image(img_bgr, page_idx)
