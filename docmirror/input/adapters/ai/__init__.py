# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
AI Backend Connector (GA1.0-ODL-01 §AI Backend Integration)
=============================================================

Provides a unified interface to LLM vision backends (GPT-4o, Gemini 2.0)
for deep pipeline analysis: chart description, complex page understanding,
and table extraction via AI.

Usage::

    from docmirror.input.adapters.ai import get_ai_backend

    backend = get_ai_backend("openai")
    result = await backend.analyze_page(page_image, {"task": "describe"})

The connector is optional — it gracefully degrades when API keys
are not configured or dependencies are not installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docmirror.input.adapters.ai.config import AIConfig, AIBackendType, get_ai_config

if TYPE_CHECKING:
    from docmirror.input.adapters.ai.protocol import AIBackend


def get_ai_backend(
    backend_type: AIBackendType | str | None = None,
    config: AIConfig | None = None,
) -> AIBackend | None:
    """Factory: return an AI backend instance or None if unavailable.

    Args:
        backend_type: One of ``"openai"``, ``"gemini"``, or ``None`` (auto-detect).
        config: Optional overrides for the default config.

    Returns:
        An AIBackend instance, or ``None`` if:
        - No backend type is specified and none can be auto-detected from env.
        - The backend's dependencies are not installed.
        - No API key is configured.
    """
    cfg = config or get_ai_config()
    bt = backend_type or cfg.default_backend

    if bt == AIBackendType.OPENAI or bt == "openai":
        return _try_create_backend("docmirror.input.adapters.ai.backends.openai", "OpenAIBackend", cfg)
    elif bt == AIBackendType.GEMINI or bt == "gemini":
        return _try_create_backend("docmirror.input.adapters.ai.backends.gemini", "GeminiBackend", cfg)
    else:
        return None


def _try_create_backend(module_path: str, class_name: str, config: AIConfig) -> AIBackend | None:
    """Try to import and instantiate a backend. Returns None on failure."""
    try:
        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        backend = cls(config)
        # Only return backend if it's actually available (has API key, etc.)
        if backend.is_available:
            return backend
        return None
    except ImportError:
        return None
    except Exception:
        return None


__all__ = [
    "AIBackend",
    "AIConfig",
    "AIBackendType",
    "get_ai_backend",
    "get_ai_config",
]
