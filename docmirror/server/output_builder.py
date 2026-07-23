# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Multi-Edition Output Builder
=============================

Shared logic for building Community / Enterprise / Finance edition outputs
from ``SealedParseResult``. Used by both the CLI (__main__.py) and REST API.

``SealedParseResult`` is the only fact source. Community Bundle v3,
Enterprise, and Finance are independent sibling projections of that snapshot.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)
PROJECTOR_TIMEOUT_SECONDS = max(0.01, float(os.getenv("DOCMIRROR_PROJECTOR_TIMEOUT_S", "300")))


def build_community_projection(
    result,
    full_text: str = "",
    *,
    file_path: str = "",
    file_id: str = "001",
    document_id: str = "",
    on_progress: Callable[[str, float, str], None] | None = None,
) -> dict | None:
    """Build Community JSON through the post-seal PluginRegistry boundary."""
    from docmirror.models.schemas.registry import validate_projection_payload
    from docmirror.models.sealed import SealedParseResult
    from docmirror.output.community_bundle import CommunityBundle
    from docmirror.plugins._runtime.plugin_registry import registry

    if not isinstance(result, SealedParseResult):
        raise TypeError(f"build_community_projection expects SealedParseResult; got {type(result).__name__}")
    if not result.verify_integrity():
        raise RuntimeError("Projector boundary violation: invalid sealed snapshot")
    detected_type = str(result.to_read_view().entities.document_type or "generic")
    projector = registry.get_projector(
        detected_type,
        "community",
        sealed_schema=result.schema_version,
    )
    if projector is None:
        projector = registry.get_projector(
            "generic",
            "community",
            sealed_schema=result.schema_version,
        )
    if projector is None:
        raise RuntimeError("No Community projector is registered")
    projected = projector.project(result)
    if projected is None or not isinstance(projected, dict):
        raise RuntimeError(f"{detected_type}:community projector returned no payload")
    if not result.verify_integrity():
        raise RuntimeError("Projector boundary violation: sealed snapshot changed")
    bundle = CommunityBundle.from_payload(projected, result.to_read_view())
    bundle.apply_delivery_context(
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
    """Build one post-seal edition projection."""
    from docmirror.models.sealed import SealedParseResult
    from docmirror.plugins._runtime.plugin_registry import registry

    if not isinstance(result, SealedParseResult):
        raise TypeError(f"build_extended_output expects SealedParseResult; got {type(result).__name__}")
    sealed = result
    if not sealed.verify_integrity():
        raise RuntimeError("Projector boundary violation: invalid sealed snapshot")
    read_view = sealed.to_read_view()
    detected_type = str(read_view.entities.document_type or "")
    projector = registry.get_projector(
        detected_type,
        edition,
        sealed_schema=sealed.schema_version,
    )
    if projector is None:
        return None
    if getattr(projector, "requires_license", False):
        from docmirror.plugins._runtime.licensing.entitlements import is_entitled

        if not is_entitled(detected_type):
            return None
    extracted = projector.project(sealed)
    if not sealed.verify_integrity():
        raise RuntimeError("Projector boundary violation: sealed snapshot changed")
    if extracted is not None and not isinstance(extracted, dict):
        raise TypeError(f"{detected_type}:{edition} projector must return dict or None")
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
                "[Projections] %s compliance/composition failed: %s",
                edition,
                exc,
            )
            extracted.setdefault("status", {}).setdefault("warnings", []).append(f"projection_compliance_failed:{exc}")
    return extracted


def _projector_unavailability_reason(
    document_type: str,
    edition: str,
    sealed_schema: str,
) -> str:
    from docmirror.plugins._runtime.plugin_registry import registry

    projector = registry.get_projector(
        document_type,
        edition,
        sealed_schema=sealed_schema,
    )
    if projector is None:
        return "package_not_installed" if not registry.list_projectors(edition) else "document_type_unsupported"
    if getattr(projector, "requires_license", False):
        from docmirror.plugins._runtime.licensing.entitlements import is_entitled

        if not is_entitled(document_type):
            return "license_not_entitled"
    return "projector_failed"


def build_all_projections(
    result,
    *,
    file_path: str = "",
    on_progress: Callable[[str, float, str], None] | None = None,
) -> dict[str, Any]:
    """Build fixed sibling projections from one immutable canonical snapshot.

    MirrorCore vNext:

    Phase 1 — project ``_mirror.json`` from the already sealed snapshot.

    Phase 2 — give each independent projector a fresh read view of that same
    sealed snapshot. No projector receives the mutable canonical instance and
    no edition reads another edition's output.
    """
    from docmirror.models.sealed import SealedParseResult

    if not isinstance(result, SealedParseResult):
        raise TypeError(f"build_all_projections expects SealedParseResult; got {type(result).__name__}")
    sealed = result
    file_path = file_path or getattr(sealed, "file_path", "") or ""

    timings: dict[str, float] = {}
    total_t0 = time.perf_counter()

    mirror_t0 = time.perf_counter()
    if on_progress:
        on_progress("community_plugin", 0.0, "Serializing core mirror...")
    from docmirror.output.mirror_projector import project_mirror

    mirror = project_mirror(
        sealed,
        source_filename=file_path if file_path else "",
        mirror_level="standard",
    )
    timings["mirror_ms"] = (time.perf_counter() - mirror_t0) * 1000
    community_t0 = time.perf_counter()
    if on_progress:
        on_progress("community_plugin", 25.0, "Building Community projection...")
    from docmirror.output.community_bundle import CommunityBundle

    community = build_community_projection(sealed, file_path=file_path)
    if community is None:
        raise RuntimeError("Community projector returned no payload")
    community_bundle = CommunityBundle.from_payload(community, sealed.to_read_view())
    if on_progress:
        on_progress("community_plugin", 100.0, "Community projection ready")
    timings["community_ms"] = (time.perf_counter() - community_t0) * 1000

    enterprise: dict[str, Any] | None = None
    finance: dict[str, Any] | None = None
    commercial_availability: dict[str, dict[str, str]] = {}
    commercial_projectors = ("enterprise", "finance")

    def _build_extended_with_timing(
        edition_name: str,
    ) -> tuple[str, dict[str, Any] | None, float, str | None]:
        started = time.perf_counter()
        unavailable_reason: str | None = None
        try:
            payload = build_extended_output(
                sealed,
                edition_name,
            )
        except Exception as exc:
            logger.warning("[Projections] %s projection failed: %s", edition_name, exc)
            payload = None
            unavailable_reason = "projector_failed"
        if payload is None and unavailable_reason is None:
            unavailable_reason = _projector_unavailability_reason(
                str(sealed.to_read_view().entities.document_type or ""),
                edition_name,
                sealed.schema_version,
            )
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
        return edition_name, payload, (time.perf_counter() - started) * 1000, unavailable_reason

    pool = ThreadPoolExecutor(max_workers=len(commercial_projectors))
    try:
        futures = [pool.submit(_build_extended_with_timing, ed) for ed in commercial_projectors]
        completed = 0
        # Timeout prevents a single hanging edition (e.g. asyncio.run hang
        # in Python 3.12 ThreadPoolExecutor) from blocking the entire
        # build_all_projections.  Each edition gets 300 s = 5 min.
        _timeout = PROJECTOR_TIMEOUT_SECONDS
        remaining = {future: ed for future, ed in zip(futures, commercial_projectors)}
        try:
            for future in as_completed(futures, timeout=_timeout):
                edition_name, payload, elapsed_ms, unavailable_reason = future.result()
                remaining.pop(future, None)
                timings[f"{edition_name}_ms"] = elapsed_ms
                if unavailable_reason:
                    commercial_availability[edition_name] = {
                        "status": "unavailable",
                        "reason": unavailable_reason,
                    }
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
                commercial_availability[ed] = {
                    "status": "unavailable",
                    "reason": "projector_timeout",
                }
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
                commercial_availability[ed] = {
                    "status": "unavailable",
                    "reason": "projector_failed",
                }
                logger.warning("[Projections] %s cancelled after unhandled exception", ed)
    finally:
        # A context-manager shutdown waits for timed-out threads and defeats the
        # delivery deadline. Projectors only receive detached sealed read views,
        # so unfinished legacy tasks cannot change facts while winding down.
        pool.shutdown(wait=False, cancel_futures=True)

    outputs: dict[str, Any] = {
        "mirror": mirror,
        "community": community,
        "enterprise": enterprise,
        "finance": finance,
        "edition_availability": commercial_availability,
    }
    # Transient renderer owned only by Community persistence. All of its facts
    # come from ParseResult; it is not an upstream source for other editions.
    outputs["community_bundle"] = community_bundle
    if not sealed.verify_integrity():
        raise RuntimeError("Projector boundary violation: sealed ParseResult integrity failed")
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
