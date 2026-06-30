# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
AI Backend Protocol — abstract interface for LLM vision backends.

Defines the ``AIBackend`` protocol (PEP 544) and associated data
types that unify OpenAI, Gemini, and future AI vision providers.

Usage::

    class MyVisionBackend:
        name = "my_vision"
        async def analyze_page(self, image, options=None):
            ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# ── Data types ───────────────────────────────────────────────────────────


@dataclass
class AIAnalysisResult:
    """Result of AI-based page analysis.

    Attributes:
        page_description: Natural language description of the page content.
        tables: List of structured table data extracted by AI vision.
        chart_descriptions: Dict mapping image/region IDs to alt-text descriptions.
        formulas: List of LaTeX formulas detected on the page.
        text_overlay: Corrected or enhanced text from AI vision.
        confidence: Overall confidence in the AI analysis [0, 1].
        raw_response: The raw API response for debugging/auditing.
        usage: Token usage information (prompt_tokens, completion_tokens, etc.).
    """

    page_description: str = ""
    tables: list[dict[str, Any]] = field(default_factory=list)
    chart_descriptions: dict[str, str] = field(default_factory=dict)
    formulas: list[str] = field(default_factory=list)
    text_overlay: str = ""
    confidence: float = 0.0
    raw_response: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class AIBackendCapabilities:
    """Capabilities declared by an AI backend."""

    vision: bool = False
    chart_description: bool = False
    table_extraction: bool = False
    formula_extraction: bool = False
    page_understanding: bool = False
    max_image_size_mb: float = 20.0
    supported_tasks: set[str] = field(default_factory=lambda: {"describe", "analyze", "extract"})


# ── Protocol ─────────────────────────────────────────────────────────────


@runtime_checkable
class AIBackend(Protocol):
    """Interface for an AI vision backend.

    A backend wraps an LLM provider (e.g. OpenAI GPT-4o, Google Gemini)
    and exposes vision-based document analysis through a unified interface.

    The protocol is implicit — any object with the required attributes
    and methods satisfies it (PEP 544 structural subtyping).
    """

    @property
    def name(self) -> str:
        """Backend name, e.g. ``'openai'``, ``'gemini'``."""
        ...

    @property
    def capabilities(self) -> AIBackendCapabilities:
        """What this backend supports."""
        ...

    @property
    def is_available(self) -> bool:
        """Whether this backend is configured and ready for use.

        Returns ``False`` when no API key is set or dependencies missing.
        """
        ...

    async def analyze_page(
        self,
        image_bytes: bytes,
        *,
        options: dict[str, Any] | None = None,
    ) -> AIAnalysisResult:
        """Analyze a page image using AI vision.

        Args:
            image_bytes: PNG or JPEG bytes of the page image.
            options: Backend-specific options dict. Common keys:
                - ``task``: ``"describe"``, ``"extract"``, or ``"analyze"``
                - ``model``: Override the default model name
                - ``language``: Hint for the document language

        Returns:
            ``AIAnalysisResult`` with structured analysis results.
        """
        ...

    async def describe_image(
        self,
        image_bytes: bytes,
        *,
        context: str = "",
        options: dict[str, Any] | None = None,
    ) -> str:
        """Generate a natural language description of an image.

        Used for chart/alt-text generation in PDF/UA output.

        Args:
            image_bytes: PNG or JPEG bytes of the image.
            context: Optional context (e.g. ``"chart"``, ``"photo"``, ``"diagram"``).
            options: Backend-specific options.

        Returns:
            Natural language description string.
        """
        ...


__all__ = [
    "AIAnalysisResult",
    "AIBackend",
    "AIBackendCapabilities",
]
