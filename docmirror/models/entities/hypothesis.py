# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Hypothesis layer models for Evidence-First Parsing Architecture (L3)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class KeyValueCandidate(BaseModel):
    """KV interpretation candidate — does not replace mirror text blocks."""

    key: str
    value: str
    confidence: float = 1.0
    method: str = "unknown"
    evidence_ids: list[str] = Field(default_factory=list)
    promoted: bool = False
    bbox: list[float] | None = None
    scope: dict[str, Any] = Field(default_factory=dict)


class ParseHypothesis(BaseModel):
    """Generic structural interpretation candidate."""

    id: str
    kind: Literal["table", "kv", "section", "document_type", "header", "field", "merge"] = "table"
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    evidence_ids: list[str] = Field(default_factory=list)
    method: str = "unknown"
    conflicts_with: list[str] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
    selected: bool = False


class TableHypothesis(ParseHypothesis):
    """Table extraction candidate with structure metadata."""

    kind: Literal["table"] = "table"
    structure_score: float = 0.0
    layer: str = ""
    row_count: int = 0
    col_count: int = 0


class MergeHypothesis(ParseHypothesis):
    """Cross-page table merge candidate."""

    kind: Literal["merge"] = "merge"
    source_table_ids: list[str] = Field(default_factory=list)
    target_page_span: list[int] = Field(default_factory=list)
    continuity_score: float = 0.0


class LogicalNodeHypothesis(ParseHypothesis):
    """Section / cover / appendix logical node (L6)."""

    kind: Literal["section"] = "section"
    node_kind: Literal["cover", "toc", "section", "appendix", "signature", "metadata", "body"] = "section"
    title: str = ""
    page_start: int | None = None
    page_end: int | None = None
    parent_id: str | None = None


class RelationHypothesis(ParseHypothesis):
    """Logical relation edge between nodes (L6 debug export)."""

    kind: Literal["field"] = "field"
    relation: Literal["belongs_to", "continues_from", "references", "signed_by", "attached_to"] = "belongs_to"
    source_id: str = ""
    target_id: str = ""
