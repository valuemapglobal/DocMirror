# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Pydantic response schemas for the DocMirror REST API.

Defines the standardized HTTP response models used by the FastAPI
endpoints in ``docmirror.server.api``.
"""
from __future__ import annotations
from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Any, List


class ParseResponse(BaseModel):
    """
    Standardized HTTP response wrapper for Document Parsing.
    Aligned with PerceptionResult.to_api_dict() output.
    """
    success: bool = Field(..., description="Whether the document was successfully parsed")
    status: str = Field(..., description="Result status: 'success', 'partial', or 'failure'")
    error: str = Field(default="", description="Error message if any")
    
    identity: Dict[str, Any] = Field(default_factory=dict, description="Identified document type and metadata")
    scene: str = Field(default="unknown", description="Detected document scene (e.g. bank_statement, invoice)")
    blocks: List[Dict[str, Any]] = Field(default_factory=list, description="Extracted content blocks (text, tables)")
    
    trust: Dict[str, Any] = Field(default_factory=dict, description="Validation scores and forgery detection")
    diagnostics: Dict[str, Any] = Field(default_factory=dict, description="Performance and pipeline diagnostics")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "success": True,
            "status": "success",
            "error": "",
            "identity": {"document_type": "bank_statement", "page_count": 3, "properties": {}},
            "scene": "bank_statement",
            "blocks": [{"type": "text", "content": "Total: $100"}],
            "trust": {"validation_score": 100, "is_forged": False},
            "diagnostics": {"elapsed_ms": 1500, "parser": "DocMirror"}
        }
    })