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

Output follows the v2.0 schema for community/enterprise and v3.0 for finance.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from docmirror.output.dmir import serialize_dmir

logger = logging.getLogger(__name__)


def build_community_output(
    result,
    full_text: str = "",
    *,
    file_path: str = "",
    on_progress: Callable[[str, float, str], None] | None = None,
) -> dict | None:
    """Build the final Community v2.1 consumer output without mutating Mirror."""
    from docmirror.plugins._runtime.community import is_community_premium
    from docmirror.plugins._runtime.composition import CompositionReason, annotate_composition
    from docmirror.plugins._runtime.runner import run_plugin_extract_sync

    out = run_plugin_extract_sync(
        result,
        edition="community",
        full_text=full_text,
        file_path=file_path,
        on_progress=on_progress,
    )
    if out is None:
        from docmirror.plugins._base.generic_mirror_adapter import build_generic_community_output

        detected_type = str(getattr(getattr(result, "entities", None), "document_type", "") or "generic")
        out = build_generic_community_output(result, detected_type if detected_type else "generic", full_text)
    if out is None:
        return None

    plugin_name = (out.get("plugin") or {}).get("name", "")
    meta = out.setdefault("metadata", {})
    if plugin_name == "generic":
        meta["community_tier"] = "generic_fallback"
        meta["community_route"] = "generic.community_plugin"
    elif is_community_premium(plugin_name):
        meta["community_tier"] = "core_domain"
        meta["community_route"] = plugin_name
    elif (out.get("status") or {}).get("warnings") and any("mirror_only" in str(w) for w in out["status"]["warnings"]):
        meta["community_tier"] = "enterprise_only"
        meta["community_route"] = "mirror_only"
        annotate_composition(out, edition="community", reason=CompositionReason.MIRROR_ONLY)
    if "composition" not in out:
        annotate_composition(out, edition="community", reason=CompositionReason.INDEPENDENT_EXTRACT)
    # Community JSON is the default standalone business artifact.  Always add
    # compact source-fact counts and projection lineage, even when callers do
    # not request the optional Mirror file on disk.
    _enrich_edition_metadata(out, result, "community", evidence_depth="standard")
    return out


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
    full_text: str = "",
    file_path: str = "",
    *,
    community_baseline: dict | None = None,
    on_progress: Callable[[str, float, str], None] | None = None,
) -> dict | None:
    """Build enterprise/finance edition output via PEC plugin runner."""
    from docmirror.plugins._runtime.runner import run_plugin_extract_sync

    detected_type = getattr(result.entities, "document_type", "")
    extracted = run_plugin_extract_sync(
        result,
        edition=edition,  # type: ignore[arg-type]
        full_text=full_text,
        file_path=file_path,
        community_baseline=community_baseline,
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
    full_text: str = "",
    file_path: str = "",
    mirror_level: str = "standard",
    include_text: bool = False,
    request_id: str = "",
    mirror_schema: str = "config",
    editions: tuple[str, ...] | None = None,
    on_progress: Callable[[str, float, str], None] | None = None,
) -> dict[str, dict[str, Any] | None]:
    """Build mirror + edition payloads from one ``ParseResult`` SSOT.

    MirrorCore vNext:

    Phase 1 — build canonical UDTR ``_mirror.json`` before any plugin runs,
    so the Mirror output is never mutated by post-extract hooks.

    Phase 2 — edition extracts (community first; extended editions reuse community
    baseline on fallback paths). Hooks may enrich edition JSON only.
    """
    full_text = full_text or getattr(result, "full_text", "") or ""
    file_path = file_path or getattr(result, "file_path", "") or ""
    from docmirror.models.entities.parse_result import ParseResult
    from docmirror.models.mirror.vnext import MirrorJsonVNext

    mirror_source = result
    edition_source = result
    is_parse_result = isinstance(result, ParseResult)
    want = (("community", "enterprise", "finance") if editions is None else editions or ()) if is_parse_result else ()
    timings: dict[str, float] = {}
    total_t0 = time.perf_counter()

    # Clear run-scoped plugin extract cache so stale results from a previous
    # document don't cause incorrect hits for this document.
    from docmirror.plugins._runtime.runner import clear_run_cache

    clear_run_cache()

    mirror_t0 = time.perf_counter()
    if on_progress:
        on_progress("community_plugin", 0.0, "Serializing core mirror...")
    if isinstance(result, MirrorJsonVNext):
        mirror = result.model_dump(by_alias=True, exclude_none=True)
    elif isinstance(result, dict) and (result.get("mirror") or {}).get("schema") == "docmirror.mirror_json":
        mirror = dict(result)
    elif is_parse_result and hasattr(mirror_source, "to_mirror_json_vnext"):
        mirror = mirror_source.to_mirror_json_vnext(
            source_filename=file_path if file_path else "",
            mirror_level=mirror_level,
        )
    else:
        raise TypeError(
            "build_all_projections expects ParseResult, MirrorJsonVNext, "
            "or a canonical Mirror JSON dict; "
            f"got {type(result).__name__}"
        )
    if is_parse_result:
        _attach_runtime_mirror_cache(mirror_source, mirror)
    timings["mirror_ms"] = (time.perf_counter() - mirror_t0) * 1000
    # DMIR projection — lossless, versioned LLM framework format (GA1.0-ODL-06)
    dmir = None
    if is_parse_result:
        dmir_t0 = time.perf_counter()
        if on_progress:
            on_progress("community_plugin", 25.0, "Building DMIR projection...")
        dmir = serialize_dmir(mirror_source)
        timings["dmir_ms"] = (time.perf_counter() - dmir_t0) * 1000

    community: dict[str, Any] | None = None
    if "community" in want or "enterprise" in want or "finance" in want:
        community_t0 = time.perf_counter()
        if on_progress:
            on_progress("community_plugin", 50.0, "Building community edition output...")
        community = build_community_output(edition_source, full_text, file_path=file_path)
        if on_progress:
            on_progress("community_plugin", 100.0, "Community edition complete")
        timings["community_ms"] = (time.perf_counter() - community_t0) * 1000

    enterprise: dict[str, Any] | None = None
    finance: dict[str, Any] | None = None
    extended_want = [ed for ed in ("enterprise", "finance") if ed in want]

    def _build_extended_with_timing(edition_name: str) -> tuple[str, dict[str, Any] | None, float]:
        started = time.perf_counter()
        try:
            payload = build_extended_output(
                edition_source,
                edition_name,
                full_text,
                file_path,
                community_baseline=community,
            )
        except Exception as exc:
            logger.warning("[Projections] %s projection failed: %s", edition_name, exc)
            payload = {
                "edition": edition_name,
                "status": {
                    "success": False,
                    "warnings": [],
                    "errors": [f"projection_failed:{exc}"],
                },
            }
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
                if payload is None:
                    payload = {
                        "edition": edition_name,
                        "status": {
                            "success": False,
                            "warnings": [],
                            "errors": [f"composition_failed:{exc}"],
                        },
                    }
        return edition_name, payload, (time.perf_counter() - started) * 1000

    if extended_want:
        with ThreadPoolExecutor(max_workers=min(2, len(extended_want))) as pool:
            futures = [pool.submit(_build_extended_with_timing, ed) for ed in extended_want]
            completed = 0
            # Timeout prevents a single hanging edition (e.g. asyncio.run hang
            # in Python 3.12 ThreadPoolExecutor) from blocking the entire
            # build_all_projections.  Each edition gets 300 s = 5 min.
            _timeout = 300.0
            remaining = {future: ed for future, ed in zip(futures, extended_want)}
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
                        sub_pct = (completed / len(extended_want)) * 100.0
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

    outputs: dict[str, dict[str, Any] | None] = {
        "mirror": mirror,
        "community": community if "community" in want else None,
        "enterprise": enterprise,
        "finance": finance,
        "dmir": dmir,
    }
    timings["total_ms"] = (time.perf_counter() - total_t0) * 1000
    logger.info(
        "[Projections] build",
        extra={
            "event": "projection_build",
            "timings": {key: round(value, 2) for key, value in timings.items()},
            "editions": ["mirror", *list(want)],
        },
    )
    return outputs


def _attach_runtime_mirror_cache(parse_result: Any, mirror: dict[str, Any]) -> None:
    """Expose the already-built vNext Mirror to edition-only recoveries.

    Bank scanned-table recovery reads Mirror blocks to reconstruct implicit
    ledger grids.  Without this runtime cache it calls ``to_mirror_json_vnext``
    again during community/enterprise/finance projection, duplicating the most
    expensive output-stage work.  This is deliberately a transient attribute:
    it does not rewrite physical ParseResult tables or edition payloads.
    """
    if not isinstance(mirror, dict) or not mirror:
        return
    try:
        parse_result._runtime_mirror_cache = mirror
    except Exception:
        logger.debug("[Projections] unable to attach runtime mirror cache", exc_info=True)


def _resolve_mirror_core_config(mirror_schema: str | None) -> dict[str, str]:
    from docmirror.configs.runtime.settings import DocMirrorSettings

    settings = DocMirrorSettings.from_env()
    schema = (mirror_schema or "config").strip().lower()
    if schema == "config":
        schema = settings.mirror_core_schema.strip().lower()
    if schema != "vnext":
        logger.warning("[MirrorCore] unsupported mirror schema %r; vNext is the only supported mirror schema", schema)
        schema = "vnext"
    return {
        "schema": schema,
        "profile": settings.mirror_core_profile,
        "engine_version": settings.mirror_core_engine_version,
    }


def _resolve_vnext_profile(mirror_level: str | None, *, default: str) -> str:
    level = (mirror_level or "").strip().lower()
    if level in {"compact", "canonical_compact"}:
        return "canonical_compact"
    if level in {"forensic"}:
        return "forensic"
    if level in {"full", "standard", "ga_full", "canonical_full"}:
        return "canonical_full"
    return default or "canonical_full"


def _license_delivery_payload() -> dict[str, Any]:
    from docmirror.plugins._runtime.licensing.lifecycle import lifecycle_cli_message, resolve_entitlement_lifecycle
    from docmirror.plugins._runtime.licensing.snapshot import resolve_license_snapshot

    lc = resolve_entitlement_lifecycle()
    snapshot = resolve_license_snapshot()
    return {
        "lifecycle_state": lc.state.value,
        "days_remaining": lc.days_remaining,
        "active_channel": snapshot.get("active_channel"),
        "renewal_url": lc.renewal_url,
        "message": lifecycle_cli_message(lc),
    }


def _attach_vnext_delivery_context(
    mirror: dict[str, Any],
    *,
    document_id: str,
    task_id: str,
    file_id: str,
    request_id: str,
    license_payload: dict[str, Any],
) -> None:
    if (mirror.get("mirror") or {}).get("schema") != "docmirror.mirror_json":
        mirror["document_id"] = document_id
        mirror.setdefault("metadata", {})
        mirror["metadata"]["task_id"] = task_id
        mirror["metadata"]["file_id"] = file_id
        mirror.setdefault("meta", {})["license"] = license_payload
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
    provenance["license"] = license_payload
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
    edition: str = "all",
    include_text: bool = False,
    mirror_level: str = "standard",
    task_id: str = "",
    file_id: str = "001",
    file_path: str = "",
    on_progress: Callable[[str, float, str], None] | None = None,
) -> dict:
    """Build vNext REST payload with optional multi-edition sidecars.

    Args:
        result: ParseResult from perceive_document
        edition: "community", "enterprise", "finance", or "all" (default)
        include_text: Include full markdown text in mirror output
        task_id: Task identifier (e.g. "20260613_084225_07e4"). Auto-generated if empty.
        file_id: File sequence number within task (default "001")

    Returns:
        vNext mirror dict. Delivery identifiers, license state, and optional
        sidecar payloads are recorded under ``source.provenance`` so the
        canonical top-level mirror shape remains document-only.
    """
    import uuid as _uuid

    # Generate task_id if not provided
    if not task_id:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_id = _uuid.uuid4().hex[:4]
        task_id = f"{ts}_{short_id}"

    document_id = f"doc_{task_id}_{file_id}"

    full_text = getattr(result, "full_text", "") or ""

    if edition == "all":
        editions_wanted: tuple[str, ...] = ("community", "enterprise", "finance")
    elif edition in ("community", "enterprise", "finance"):
        editions_wanted = (edition,)
    else:
        editions_wanted = ()

    request_id = str(_uuid.uuid4())
    projections = build_all_projections(
        result,
        full_text=full_text,
        file_path=file_path,
        mirror_level=mirror_level,
        include_text=include_text,
        request_id=request_id,
        editions=editions_wanted,
        on_progress=on_progress,
    )
    mirror = projections["mirror"]

    editions_map = {}
    for ed in editions_wanted:
        ed_data = projections.get(ed)
        if ed_data is not None:
            ed_data.setdefault("document", {})["document_id"] = document_id
            ed_data.setdefault("metadata", {})
            ed_data["metadata"]["task_id"] = task_id
            ed_data["metadata"]["file_id"] = file_id
            editions_map[ed] = ed_data

    # DMIR output — lossless, versioned LLM framework format
    dmir_output = projections.get("dmir")
    if editions_map or dmir_output is not None:
        provenance = mirror.setdefault("source", {}).setdefault("provenance", {})
        provenance["sidecars"] = {
            "editions": editions_map,
            "dmir": dmir_output,
        }

    _attach_vnext_delivery_context(
        mirror,
        document_id=document_id,
        task_id=task_id,
        file_id=file_id,
        request_id=request_id,
        license_payload=_license_delivery_payload(),
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
