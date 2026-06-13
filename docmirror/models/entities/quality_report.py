# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Parse quality report model for evaluation loop (L6)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ParseQualityReport(BaseModel):
    """Unified quality report for a single parse run."""

    document_id: str = ""
    parser_version: str = ""
    metrics: dict[str, float] = Field(default_factory=dict)
    failures: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    failure_class: str | None = None
    gate_passed: bool | None = None
    debug_artifact_path: str | None = None
    regression_delta: dict[str, float] = Field(default_factory=dict)
