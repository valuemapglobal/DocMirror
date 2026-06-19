# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Debug artifact — structured JSON debug bundle writer.

Purpose: Builds and writes debug artifacts capturing blocks, timings, and
extraction lineage when ``is_debug_mode()`` is active.

Main components: ``build_debug_artifact``, ``write_debug_artifact``,
``is_debug_mode``.

Upstream: Pipeline completion hooks, provenance metadata.

Downstream: Filesystem debug output, ``_ehl_annex`` integrations.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docmirror.models.entities.parse_result import MirrorAnnex, ParseResult


def _ehl_annex(result: ParseResult) -> MirrorAnnex | None:
    """Return EHL annex when populated."""
    annex = getattr(result, "annex", None)
    if annex is None:
        return None
    if annex.hypotheses or annex.evidence_summary or annex.quality_report:
        return annex
    return None


def _annex_payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


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

    annex = _ehl_annex(result)
    if annex:
        if annex.hypotheses:
            artifact["hypotheses"] = [_annex_payload(h) for h in annex.hypotheses]
        if annex.evidence_summary:
            artifact["evidence_summary"] = _annex_payload(annex.evidence_summary)
        if annex.quality_report:
            artifact["quality_report"] = _annex_payload(annex.quality_report)
        if annex.pipeline_debug:
            artifact["pipeline_debug"] = annex.pipeline_debug

    if evidence_spans:
        artifact["evidence_spans"] = evidence_spans

    if crop_manifest:
        artifact["crop_manifest"] = crop_manifest

    # Table composition operations (for cross-page merge debugging)
    if result.table_operations:
        artifact["table_operations"] = result.table_operations

    if result.sections:
        artifact["sections"] = result.sections

    if resolver_decisions:
        artifact["resolver_decisions"] = resolver_decisions

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
    if spans:
        from docmirror.models.ehl import attach_spans_annex

        attach_spans_annex(result, spans)
    if pdf_path and is_debug_mode() and spans:
        bbox_spans = [
            s
            for s in spans
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

    from docmirror.models.serialization import dumps_json

    artifact = build_debug_artifact(
        result,
        resolver_decisions=resolver_decisions,
        extra=extra,
        evidence_spans=spans or evidence_spans,
        crop_manifest=crop_manifest,
    )
    path.write_text(dumps_json(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def is_debug_mode() -> bool:
    """True when DOCMIRROR_DEBUG=1 or debug artifact requested."""
    return os.environ.get("DOCMIRROR_DEBUG", "").strip() in ("1", "true", "yes")
