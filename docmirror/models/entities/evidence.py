# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Physical evidence models for Evidence-First Parsing Architecture (L1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceSpan(BaseModel):
    """Atomic physical evidence unit with stable ID for provenance tracing."""

    id: str
    page: int
    kind: Literal["char", "word", "line", "rect", "image", "ocr_token"] = "word"
    text: str = ""
    bbox: list[float] | None = None
    confidence: float = 1.0
    source: Literal["pdf_text", "ocr", "layout_model", "derived"] = "pdf_text"
    attrs: dict[str, Any] = Field(default_factory=dict)


class TrustEvidence(BaseModel):
    """Unified trust/forgery evidence attached to parse results."""

    trust_score: float = 1.0
    forgery_detected: bool = False
    forgery_reasons: list[str] = Field(default_factory=list)
    cache_mode: str = "fast"
    file_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceSummary(BaseModel):
    """Lightweight evidence index attached to ParseResult (debug/eval only)."""

    total_spans: int = 0
    span_ids: list[str] = Field(default_factory=list)
    by_source: dict[str, int] = Field(default_factory=dict)
    by_page: dict[int, int] = Field(default_factory=dict)
