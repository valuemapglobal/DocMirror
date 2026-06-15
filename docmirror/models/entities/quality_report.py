# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Parse quality report model for the evaluation loop (L6).

``ParseQualityReport`` captures unified quality metrics for a single parse run,
used by benchmark CLI, regression gates, and debug artifact export.

Fields::

    document_id / parser_version     Run identification
    metrics                          Named float metrics (coverage, F1, latency, …)
    failures / warnings              Structured failure records and warning strings
    failure_class / gate_passed      Regression gate classification
    debug_artifact_path              Path to dumped debug bundle
    regression_delta                 Metric deltas vs baseline

Attached to ``ParseResult.annex.quality_report`` via ``ehl.attach_quality_report_annex``.
"""

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
