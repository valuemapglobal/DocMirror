# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
AI Backend Configuration (GA1.0-ODL-01 §AI Backend Config)
============================================================

Manages API keys, model selection, rate limiting, and backend
auto-detection for all AI vision providers.

Configuration is loaded from environment variables:

=============  ============================================
Env Variable   Purpose
=============  ============================================
``DOCMIRROR_AI_BACKEND``  Default backend (``openai`` or ``gemini``)
``OPENAI_API_KEY``        OpenAI API key
``OPENAI_MODEL``          Model name override (default: ``gpt-4o``)
``GEMINI_API_KEY``        Google Gemini API key
``GEMINI_MODEL``          Model name override (default: ``gemini-2.0-flash``)
``DOCMIRROR_AI_RATE_LIMIT``  Max API calls per second (default: 10)
=============  ============================================
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Backend types ────────────────────────────────────────────────────────


class AIBackendType(str, Enum):
    """Supported AI backend providers."""

    OPENAI = "openai"
    GEMINI = "gemini"


# ── Default model constants ──────────────────────────────────────────────

DEFAULT_OPENAI_MODEL = "gpt-4o"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

# ── Rate limiting ────────────────────────────────────────────────────────

DEFAULT_RATE_LIMIT = 10  # API calls per second
MAX_RETRIES = 3
BASE_RETRY_DELAY_MS = 1000


@dataclass
class AIConfig:
    """Configuration for AI backends.

    Loaded from environment variables by default, but can be
    constructed programmatically for testing or custom setups.
    """

    # ── Provider selection ──
    default_backend: AIBackendType = AIBackendType.OPENAI

    # ── OpenAI ──
    openai_api_key: str = ""
    openai_model: str = DEFAULT_OPENAI_MODEL
    openai_base_url: str = ""  # Optional: for proxies / Azure OpenAI
    openai_max_tokens: int = 4096
    openai_temperature: float = 0.3

    # ── Gemini ──
    gemini_api_key: str = ""
    gemini_model: str = DEFAULT_GEMINI_MODEL
    gemini_max_tokens: int = 8192
    gemini_temperature: float = 0.3

    # ── Rate limiting ──
    rate_limit_per_second: int = DEFAULT_RATE_LIMIT

    def to_dict(self) -> dict[str, Any]:
        """Serialize config to dict (excluding secrets)."""
        return {
            "default_backend": self.default_backend.value,
            "openai_model": self.openai_model,
            "openai_base_url": self.openai_base_url or "(default)",
            "gemini_model": self.gemini_model,
            "rate_limit_per_second": self.rate_limit_per_second,
        }


def get_ai_config() -> AIConfig:
    """Load AI configuration from environment variables.

    Returns:
        A fully populated ``AIConfig`` based on the current environment.
    """
    # Detect default backend
    backend_str = os.environ.get("DOCMIRROR_AI_BACKEND", "").lower()
    if backend_str == "gemini":
        default_backend = AIBackendType.GEMINI
    elif backend_str == "openai":
        default_backend = AIBackendType.OPENAI
    elif os.environ.get("OPENAI_API_KEY"):
        default_backend = AIBackendType.OPENAI
    elif os.environ.get("GEMINI_API_KEY"):
        default_backend = AIBackendType.GEMINI
    else:
        default_backend = AIBackendType.OPENAI

    # Parse rate limit
    try:
        rate_limit = int(os.environ.get("DOCMIRROR_AI_RATE_LIMIT", str(DEFAULT_RATE_LIMIT)))
    except (ValueError, TypeError):
        rate_limit = DEFAULT_RATE_LIMIT

    return AIConfig(
        default_backend=default_backend,
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        openai_model=os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        openai_base_url=os.environ.get("OPENAI_BASE_URL", ""),
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        gemini_model=os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        rate_limit_per_second=rate_limit,
    )


__all__ = [
    "AIConfig",
    "AIBackendType",
    "get_ai_config",
    "DEFAULT_OPENAI_MODEL",
    "DEFAULT_GEMINI_MODEL",
    "DEFAULT_RATE_LIMIT",
    "MAX_RETRIES",
    "BASE_RETRY_DELAY_MS",
]
