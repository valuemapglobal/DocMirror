# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Pydantic response schemas for the DocMirror REST API.

Successful parse endpoints return vNext mirror JSON directly, without the
removed ``code/message/data`` REST envelope.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ParseResponse(BaseModel):
    """vNext mirror JSON response for document parsing."""

    mirror: dict[str, Any] = Field(default_factory=dict, description="Mirror schema and engine metadata")
    source: dict[str, Any] = Field(default_factory=dict, description="Source file metadata")
    document: dict[str, Any] = Field(default_factory=dict, description="Document identity and type candidates")
    pages: list[dict[str, Any]] = Field(default_factory=list, description="Page topology")
    evidence: dict[str, Any] = Field(default_factory=dict, description="Evidence atoms and indexes")
    regions: list[dict[str, Any]] = Field(default_factory=list, description="Reconstructed page regions")
    blocks: list[dict[str, Any]] = Field(default_factory=list, description="Document blocks")
    graph: dict[str, Any] = Field(default_factory=dict, description="Reading/order graph")
    semantics: dict[str, Any] = Field(default_factory=dict, description="Semantic facts and views")
    quality: dict[str, Any] = Field(default_factory=dict, description="Quality gates and diagnostics")
    diagnostics: dict[str, Any] = Field(default_factory=dict, description="Diagnostics")
    assets: dict[str, Any] = Field(default_factory=dict, description="Asset references")
    meta: dict[str, Any] = Field(default_factory=dict, description="Server-side metadata and license state")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mirror": {"schema": "docmirror.mirror_json", "schema_version": "1.0.5"},
                "source": {"filename": "statement.pdf"},
                "document": {"document_type": "bank_statement", "document_type_candidates": []},
                "pages": [],
                "evidence": {"text_atoms": []},
                "regions": [],
                "blocks": [],
                "graph": {},
                "semantics": {"facts": [], "entities": [], "views": {}},
                "quality": {"overall": {"status": "pass", "score": 1.0}},
                "diagnostics": {},
                "assets": {},
                "meta": {},
            }
        }
    )
