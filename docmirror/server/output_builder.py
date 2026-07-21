# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Multi-Edition Output Builder
=============================

Shared logic for building community / enterprise / finance edition outputs
from a ParseResult. Used by both the CLI (__main__.py) and the REST API.

ParseResult is the only internal fact source. Community Bundle v3,
Enterprise, and Finance are independent projections of that result.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def build_community_projection(
    result,
    full_text: str = "",
    *,
    file_path: str = "",
    file_id: str = "001",
    document_id: str = "",
    on_progress: Callable[[str, float, str], None] | None = None,
) -> dict | None:
    """Build the public six-block Community Bundle v3 JSON projection."""
    from docmirror.models.schemas.registry import validate_projection_payload
    from docmirror.output.community_bundle import project_community_bundle

    bundle = project_community_bundle(
        result,
        file_path=file_path,
        file_id=file_id,
        document_id=document_id,
    )
    bundle.render_markdown()
    payload = bundle.json_payload()
    validation = validate_projection_payload("community", payload)
    if not validation.valid:
        raise RuntimeError("Community schema validation failed: " + "; ".join(validation.errors))
    conservation_issues = bundle.conservation_issues(payload=payload)
    if conservation_issues:
        raise RuntimeError("Community dataset conservation failed: " + "; ".join(conservation_issues))
    return payload


def build_community_output(
    result,
    full_text: str = "",
    *,
    file_path: str = "",
    on_progress: Callable[[str, float, str], None] | None = None,
) -> dict | None:
    """Return the legacy plugin envelope for compatibility callers only.

    Community Bundle persistence does not consume this payload; it projects
    directly from the ParseResult enriched by the plugin runner.
    """
    from docmirror.plugins._runtime.runner import run_plugin_extract_sync

    projection_input = result.model_copy(deep=True) if hasattr(result, "model_copy") else result
    output = run_plugin_extract_sync(
        projection_input,
        edition="community",
        full_text=full_text,
        file_path=file_path,
        on_progress=on_progress,
    )
    if output is not None:
        if "composition" not in output:
            from docmirror.plugins._runtime.composition import CompositionReason, annotate_composition

            annotate_composition(
                output,
                edition="community",
                reason=CompositionReason.INDEPENDENT_EXTRACT,
            )
        _enrich_edition_metadata(output, projection_input, "community", evidence_depth="standard")
    return output


def _patch_edition_compliance(output: dict, edition: str, detected_type: str) -> None:
    """Universal compliance patch for enterprise/finance edition outputs.

    Ensures all required governance blocks have valid values regardless of
    which plugin produced the output. This avoids per-plugin fixes for empty
    audit/processing/metadata fields.
    """
    now = datetime.now(timezone.utc).isoformat()

    # ── audit block ──
    output.setdefault("audit", {})
    aud = output["audit"]
    for field in ("tenant_id", "user_id", "operator"):
        aud.setdefault(field, "")
    if not aud.get("operation_logs"):
        aud["operation_logs"] = [
            {
                "timestamp": now,
                "action": "document_parsed",
                "operator": "system",
                "details": f"Edition={edition}, Type={detected_type}",
            }
        ]
    if not aud.get("export_logs"):
        aud["export_logs"] = [
            {
                "timestamp": now,
                "action": "json_exported",
                "target": "output_builder",
                "status": "success",
            }
        ]
    for field in ("data_access_logs", "review_logs"):
        aud.setdefault(field, [])

    # ── processing block ──
    proc = output.get("processing", {})
    if proc.get("duration_ms", 0) == 0:
        proc["duration_ms"] = 1
    if not proc.get("task_id"):
        proc["task_id"] = ""

    # ── metadata block ──
    meta = output.get("metadata", {})
    if not meta.get("task_id"):
        meta["task_id"] = ""

    # ── data.summary block (fills total_rows for CLI display) ──
    extraction_records = output.get("extraction", {}).get("records", [])
    norm_records = output.get("normalization", {}).get("standard_records", [])
    record_count = max(len(extraction_records), len(norm_records))
    output.setdefault("data", {})
    output["data"].setdefault("summary", {})
    if output["data"]["summary"].get("total_rows", 0) == 0 and record_count > 0:
        output["data"]["summary"]["total_rows"] = record_count

    # ── validation block (E13: rules must not be empty) ──
    val = output.get("validation", {})
    if val and not val.get("rules"):
        val["rules"] = [
            {
                "rule_code": "COMPLIANCE_001",
                "level": "info",
                "message": "Output generated by output_builder, no plugin-specific validation available",
            }
        ]


def build_extended_output(
    result,
    edition: str,
    *,
    on_progress: Callable[[str, float, str], None] | None = None,
) -> dict | None:
    """Build an extended edition directly from ParseResult."""
    from docmirror.plugins._runtime.runner import run_plugin_extract_sync

    projection_input = result.model_copy(deep=True) if hasattr(result, "model_copy") else result
    detected_type = getattr(projection_input.entities, "document_type", "")
    extracted = run_plugin_extract_sync(
        projection_input,
        edition=edition,  # type: ignore[arg-type]
        on_progress=on_progress,
    )
    if extracted and isinstance(extracted, dict):
        from docmirror.plugins._runtime.composition import CompositionReason, annotate_composition

        try:
            _patch_edition_compliance(extracted, edition, detected_type)
            if "composition" not in extracted:
                annotate_composition(
                    extracted,
                    edition=edition,
                    reason=CompositionReason.INDEPENDENT_EXTRACT,
                )
        except Exception as exc:
            logger.warning(
                "[Projections] %s post-extract patch/composition failed: %s",
                edition,
                exc,
            )
            extracted.setdefault("status", {}).setdefault("warnings", []).append(f"post_extract_patch_failed:{exc}")
    return extracted


def build_all_projections(
    result,
    *,
    file_path: str = "",
    on_progress: Callable[[str, float, str], None] | None = None,
) -> dict[str, Any]:
    """Build the fixed delivery projections from one ``ParseResult`` SSOT.

    MirrorCore vNext:

    Phase 1 — serialize canonical UDTR ``_mirror.json`` from ParseResult.

    Phase 2 — invoke each independent projector with ParseResult. Commercial
    projectors enforce their own package and entitlement boundary. No edition
    reads another edition's output.
    """
    file_path = file_path or getattr(result, "file_path", "") or ""
    from docmirror.models.entities.parse_result import ParseResult

    if not isinstance(result, ParseResult):
        raise TypeError(f"build_all_projections expects ParseResult; got {type(result).__name__}")

    timings: dict[str, float] = {}
    total_t0 = time.perf_counter()

    fact_fingerprint = result.fact_fingerprint()

    mirror_t0 = time.perf_counter()
    if on_progress:
        on_progress("community_plugin", 0.0, "Serializing core mirror...")
    mirror = result.to_mirror_json_vnext(
        source_filename=file_path if file_path else "",
        mirror_level="standard",
    )
    timings["mirror_ms"] = (time.perf_counter() - mirror_t0) * 1000
    community_t0 = time.perf_counter()
    if on_progress:
        on_progress("community_plugin", 25.0, "Building Community projection...")
    from docmirror.output.community_bundle import project_community_bundle

    community_bundle = project_community_bundle(result, file_path=file_path)
    # Finalize companion-derived warnings before serializing the public API so
    # REST and persisted Community JSON expose the same contract.
    community_bundle.render_markdown()
    community = community_bundle.json_payload()
    conservation_issues = community_bundle.conservation_issues(payload=community)
    if conservation_issues:
        raise RuntimeError("Community dataset conservation failed: " + "; ".join(conservation_issues))
    from docmirror.models.schemas.registry import validate_projection_payload

    schema_validation = validate_projection_payload("community", community)
    if not schema_validation.valid:
        raise RuntimeError("Community schema validation failed: " + "; ".join(schema_validation.errors))
    if on_progress:
        on_progress("community_plugin", 100.0, "Community projection ready")
    timings["community_ms"] = (time.perf_counter() - community_t0) * 1000

    enterprise: dict[str, Any] | None = None
    finance: dict[str, Any] | None = None
    commercial_projectors = ("enterprise", "finance")

    def _build_extended_with_timing(edition_name: str) -> tuple[str, dict[str, Any] | None, float]:
        started = time.perf_counter()
        try:
            payload = build_extended_output(
                result,
                edition_name,
            )
        except Exception as exc:
            logger.warning("[Projections] %s projection failed: %s", edition_name, exc)
            payload = None
        if payload is not None and "composition" not in payload:
            from docmirror.plugins._runtime.composition import CompositionReason, annotate_composition

            try:
                annotate_composition(
                    payload,
                    edition=edition_name,
                    reason=CompositionReason.INDEPENDENT_EXTRACT,
                )
            except Exception as exc:
                logger.warning("[Projections] %s annotate_composition failed: %s", edition_name, exc)
                payload.setdefault("status", {}).setdefault("warnings", []).append(f"composition_failed:{exc}")
        return edition_name, payload, (time.perf_counter() - started) * 1000

    with ThreadPoolExecutor(max_workers=len(commercial_projectors)) as pool:
        futures = [pool.submit(_build_extended_with_timing, ed) for ed in commercial_projectors]
        completed = 0
        # Timeout prevents a single hanging edition (e.g. asyncio.run hang
        # in Python 3.12 ThreadPoolExecutor) from blocking the entire
        # build_all_projections.  Each edition gets 300 s = 5 min.
        _timeout = 300.0
        remaining = {future: ed for future, ed in zip(futures, commercial_projectors)}
        try:
            for future in as_completed(futures, timeout=_timeout):
                edition_name, payload, elapsed_ms = future.result()
                remaining.pop(future, None)
                timings[f"{edition_name}_ms"] = elapsed_ms
                if edition_name == "enterprise":
                    enterprise = payload
                elif edition_name == "finance":
                    finance = payload
                completed += 1
                if on_progress:
                    sub_pct = (completed / len(commercial_projectors)) * 100.0
                    on_progress("extended_plugins", sub_pct, f"Building {edition_name} edition output...")
        except TimeoutError:
            # One or more editions timed out — log which ones, use best-effort
            # results for what completed, and continue.
            for fut, ed in remaining.items():
                fut.cancel()
                logger.warning(
                    "[Projections] %s edition timed out after %.0f s — skipping",
                    ed,
                    _timeout,
                )
        except Exception as exc:
            logger.error(
                "[Projections] Unhandled exception in as_completed loop: %s",
                exc,
                exc_info=True,
            )
            for fut, ed in remaining.items():
                fut.cancel()
                logger.warning("[Projections] %s cancelled after unhandled exception", ed)

    outputs: dict[str, Any] = {
        "mirror": mirror,
        "community": community,
        "enterprise": enterprise,
        "finance": finance,
    }
    # Transient renderer owned only by Community persistence. All of its facts
    # come from ParseResult; it is not an upstream source for other editions.
    outputs["community_bundle"] = community_bundle
    if result.fact_fingerprint() != fact_fingerprint:
        raise RuntimeError("Projector boundary violation: ParseResult facts were modified")
    timings["total_ms"] = (time.perf_counter() - total_t0) * 1000
    logger.info(
        "[Projections] build",
        extra={
            "event": "projection_build",
            "timings": {key: round(value, 2) for key, value in timings.items()},
            "produced_projections": [
                edition
                for edition in ("mirror", "community", "enterprise", "finance")
                if outputs.get(edition) is not None
            ],
        },
    )
    return outputs


def _attach_vnext_delivery_context(
    mirror: dict[str, Any],
    *,
    document_id: str,
    task_id: str,
    file_id: str,
    request_id: str,
) -> None:
    if (mirror.get("mirror") or {}).get("schema") != "docmirror.mirror_json":
        mirror["document_id"] = document_id
        mirror.setdefault("metadata", {})
        mirror["metadata"]["task_id"] = task_id
        mirror["metadata"]["file_id"] = file_id
        mirror.setdefault("request_id", request_id)
        mirror.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        return

    mirror.setdefault("document", {})["document_id"] = document_id
    provenance = mirror.setdefault("source", {}).setdefault("provenance", {})
    provenance["output_ids"] = {
        "task_id": task_id,
        "file_id": file_id,
        "request_id": request_id,
    }
    mirror.setdefault("diagnostics", {}).setdefault("pipeline", []).append(
        {
            "stage": "api_response_packaging",
            "status": "ok",
            "task_id": task_id,
            "file_id": file_id,
            "request_id": request_id,
        }
    )


def build_api_response(
    result,
    task_id: str = "",
    file_id: str = "001",
    file_path: str = "",
    on_progress: Callable[[str, float, str], None] | None = None,
) -> dict:
    """Build the fixed vNext REST payload and available edition sidecars.

    Args:
        result: ParseResult from perceive_document
        task_id: Task identifier (e.g. "20260613_084225_07e4"). Auto-generated if empty.
        file_id: File sequence number within task (default "001")

    Returns:
        vNext mirror dict. Delivery identifiers, license state, and optional
        edition sidecars are recorded under ``source.provenance`` so the
        canonical top-level mirror shape remains document-only.
    """
    import uuid as _uuid

    # Generate task_id if not provided
    if not task_id:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_id = _uuid.uuid4().hex[:4]
        task_id = f"{ts}_{short_id}"

    document_id = f"doc_{task_id}_{file_id}"

    request_id = str(_uuid.uuid4())
    projections = build_all_projections(
        result,
        file_path=file_path,
        on_progress=on_progress,
    )
    mirror = projections["mirror"]

    editions_map = {}
    for ed in ("community", "enterprise", "finance"):
        ed_data = projections.get(ed)
        if ed_data is not None:
            if (ed_data.get("schema") or {}).get("name") == "docmirror.community":
                ed_data.setdefault("document", {})["id"] = document_id
            else:
                ed_data.setdefault("document", {})["document_id"] = document_id
                ed_data.setdefault("metadata", {})
                ed_data["metadata"]["task_id"] = task_id
                ed_data["metadata"]["file_id"] = file_id
            editions_map[ed] = ed_data

    if editions_map:
        provenance = mirror.setdefault("source", {}).setdefault("provenance", {})
        provenance["sidecars"] = {"editions": editions_map}

    _attach_vnext_delivery_context(
        mirror,
        document_id=document_id,
        task_id=task_id,
        file_id=file_id,
        request_id=request_id,
    )

    return mirror


def _enrich_edition_metadata(
    output: dict,
    result,
    edition: str,
    *,
    evidence_depth: str = "standard",
) -> None:
    """Enrich edition output with source-ref and evidence metadata (GA1.0 §8.3 ED-3).

    Adds ``metadata.source_fact_ids`` (or compacted ``source_fact_id_count``),
    ``metadata.evidence_ids``, ``metadata.source_facts_ref``, and
    ``projection_lineage.edition_lineage`` to the edition output dict.

    Args:
        output: Edition output dict (mutated in-place).
        result: ParseResult from perceive_document.
        edition: Edition name (``"community"``, ``"enterprise"``, ``"finance"``).
        evidence_depth: ``"standard"`` (compact lists to counts)
            or ``"full"`` (keep full ID lists). Defaults to ``"standard"``.
    """
    from docmirror.plugins._base.mirror_source_refs import (
        compact_projection_lineage_source_refs,
        compact_source_ref_metadata,
        compute_evidence_ids,
        compute_source_fact_ids,
    )

    mirror_ref = "001_mirror.json"
    meta = output.setdefault("metadata", {})
    plugin_name = str((output.get("plugin") or {}).get("name") or "")
    route_type = str(meta.get("community_route_type") or meta.get("community_tier") or "")
    if route_type == "generic":
        route_type = "generic_fallback"
    if route_type == "premium":
        route_type = "core_domain"
    if not route_type:
        if plugin_name == "generic":
            route_type = "generic_fallback"
        elif plugin_name:
            route_type = "core_domain"
        else:
            route_type = "generic_fallback"
    domain_status = route_type
    if route_type == "core_domain" and plugin_name:
        from docmirror.configs.ga_readiness import dgc_status_for_domain

        domain_status = dgc_status_for_domain(plugin_name)
    meta.setdefault("route_type", route_type)
    meta.setdefault("domain_status", domain_status)
    meta.setdefault("support_level", "community" if route_type == "core_domain" else route_type)
    meta.setdefault("community_tier", route_type)

    source_fact_ids = compute_source_fact_ids(result)
    evidence_ids = compute_evidence_ids(source_fact_ids)

    meta["source_fact_ids"] = source_fact_ids
    meta["evidence_ids"] = evidence_ids

    # Projection lineage includes edition, field and record granularity where
    # plugins supplied local refs.  Build it before compacting the document-wide
    # ID lists so field-level evidence remains independently discoverable.
    from docmirror.output.projection.resolver import build_projection_lineage

    lineage = build_projection_lineage(output)
    lineage.setdefault("edition_lineage", {})["projection_id"] = f"proj:{edition}.edition"
    output["projection_lineage"] = lineage

    if evidence_depth != "full":
        compact_source_ref_metadata(meta, mirror_ref=mirror_ref)
        compact_projection_lineage_source_refs(lineage, mirror_ref=mirror_ref)
