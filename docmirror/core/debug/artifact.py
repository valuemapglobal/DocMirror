# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Debug artifact builder for evidence-first parsing."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docmirror.models.entities.parse_result import ParseResult
from docmirror.models.entities.quality_report import ParseQualityReport


def build_debug_artifact(
    result: ParseResult,
    *,
    resolver_decisions: list[Any] | None = None,
    extra: dict[str, Any] | None = None,
    evidence_spans: list[Any] | None = None,
    crop_manifest: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build debug JSON payload from ParseResult internal fields."""
    artifact: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "document_type": result.entities.document_type,
        "page_count": result.page_count,
        "table_count": result.total_tables,
        "confidence": result.confidence,
    }

    if result.hypotheses:
        artifact["hypotheses"] = [h.model_dump() for h in result.hypotheses]

    if result.evidence_summary:
        artifact["evidence_summary"] = result.evidence_summary.model_dump()

    if evidence_spans:
        artifact["evidence_spans"] = [
            s.model_dump() if hasattr(s, "model_dump") else s for s in evidence_spans
        ]

    if crop_manifest:
        artifact["crop_manifest"] = crop_manifest

    if result.kv_candidates:
        artifact["kv_candidates"] = [kv.model_dump() for kv in result.kv_candidates]

    if result.quality_report:
        artifact["quality_report"] = result.quality_report.model_dump()

    # Table composition operations (for cross-page merge debugging)
    if result.logical_tables:
        artifact["table_operations"] = [
            {
                "table_id": lt.table_id,
                "source_pages": lt.source_pages,
                "page_span": list(lt.page_span) if hasattr(lt.page_span, '__iter__') else lt.page_span,
                "row_count": lt.row_count,
                "confidence": lt.confidence,
                "merge_log": lt.merge_log,
                "provenance": [
                    {"source_page": p.source_page, "source_row_index": p.source_row_index, "is_continuation": p.is_continuation}
                    for p in lt.provenance
                ] if lt.provenance else [],
            }
            for lt in result.logical_tables
        ]

    if resolver_decisions:
        artifact["resolver_decisions"] = [
            d.model_dump() if hasattr(d, "model_dump") else d for d in resolver_decisions
        ]

    # (logical_graph removed — DocGraph module deleted in 2026-06-11 cleanup)

    if extra:
        artifact["extra"] = extra

    return artifact


def write_debug_artifact(
    result: ParseResult,
    output_path: str | Path,
    *,
    resolver_decisions: list[Any] | None = None,
    extra: dict[str, Any] | None = None,
    pdf_path: str | Path | None = None,
    evidence_spans: list[Any] | None = None,
) -> Path:
    """Write debug artifact JSON to disk."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    crop_manifest: list[dict[str, Any]] | None = None
    spans = list(evidence_spans or [])
    if not spans and pdf_path:
        try:
            from docmirror.core.debug.crop_generator import collect_evidence_spans_from_parse_result

            spans = collect_evidence_spans_from_parse_result(result)
        except Exception:
            spans = []
    if pdf_path and is_debug_mode() and spans:
        bbox_spans = [
            s for s in spans
            if (getattr(s, "bbox", None) or (isinstance(s, dict) and s.get("bbox")))
        ]
        if bbox_spans:
            try:
                from docmirror.core.debug.crop_generator import generate_field_crops

                crop_manifest = generate_field_crops(
                    pdf_path,
                    bbox_spans,
                    path.parent / f"{path.stem}_crops",
                )
            except Exception:
                crop_manifest = None

    artifact = build_debug_artifact(
        result,
        resolver_decisions=resolver_decisions,
        extra=extra,
        evidence_spans=spans or evidence_spans,
        crop_manifest=crop_manifest,
    )
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def is_debug_mode() -> bool:
    """True when DOCMIRROR_DEBUG=1 or debug artifact requested."""
    return os.environ.get("DOCMIRROR_DEBUG", "").strip() in ("1", "true", "yes")
