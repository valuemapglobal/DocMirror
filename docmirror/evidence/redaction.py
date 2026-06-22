# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Redaction-safe support bundle builder.

GA 1.0 design §8.4 EV-5 / OUT4-3: Generates a redaction-safe support bundle that
excludes sensitive raw values while preserving bbox, field_path, quality, hash,
and evidence linkage so that support and audit teams can investigate issues
without seeing customer data.

Usage::

    from docmirror.evidence.redaction import build_support_bundle
    bundle = build_support_bundle(result, editions, evidence_bundle)
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def _hash_value(value: str) -> str:
    """Create a SHA-256 hash of a value for non-reversible redaction."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _redact_value(value: str) -> dict[str, str]:
    """Redact a single value, returning structure hints without raw content.

    Returns:
        Dict with ``hash``, ``length``, ``kind``, and optional ``prefix_char``.
    """
    if not value:
        return {"hash": _hash_value(""), "length": 0, "kind": "empty"}

    result: dict[str, str] = {
        "hash": _hash_value(value),
        "length": str(len(value)),
    }

    # Classify value type without exposing content
    if value.replace(".", "").replace(",", "").replace("-", "").replace(" ", "").isdigit():
        result["kind"] = "numeric"
    elif value.isalpha():
        result["kind"] = "alpha"
        if len(value) > 0:
            result["prefix_char"] = value[0] if value[0].isalpha() else "*"
    elif value.isalnum():
        result["kind"] = "alphanumeric"
    else:
        result["kind"] = "mixed"

    return result


def _build_minimal_repro(result: Any, editions: dict[str, Any] | None) -> dict[str, Any]:
   """Build minimal reproduction context for support bundle.

   Captures parser info, pipeline decision, format profile, and error traces
   without raw content.
   """
   repro: dict[str, Any] = {
       "parser": getattr(getattr(result, "parser_info", None), "parser_name", ""),
       "format_profile": str(
           getattr(
               getattr(getattr(result, "parser_info", None), "options", None),
               "get",
               lambda _k, _d=None: None,
           )("parse_profile", "unknown")
           if hasattr(getattr(result, "parser_info", None), "options")
           else "unknown"
       ),
       "extraction_profile": str(
           getattr(
               getattr(result, "parser_info", None),
               "extraction_profile",
               "unknown",
           )
           if hasattr(getattr(result, "parser_info", None), "extraction_profile")
           else "unknown"
       ),
       "pipeline_decision": _safe_dict(getattr(result, "pipeline_decision", None)),
       "document_type": str(
           getattr(getattr(result, "entities", None), "document_type", "")
       ),
       "page_count": len(list(getattr(result, "pages", []) or [])),
       "errors": [
           str(e) for e in (getattr(getattr(result, "errors", None), "get", lambda: [])() or [])
       ],
       "editions_available": [
           ed for ed in (editions or {}) if (editions or {}).get(ed) is not None
       ],
   }
   return repro


def _safe_dict(obj: Any) -> dict[str, Any] | None:
    """Safely convert an object to dict if possible, returning None otherwise."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    try:
        return dict(obj)
    except (TypeError, ValueError):
        return {"_repr": str(obj)[:200]}


def build_support_bundle(
    result: Any,
    *,
    editions: dict[str, Any] | None = None,
    evidence_bundle: dict[str, Any] | None = None,
    task_id: str = "",
    document_id: str = "",
    file_id: str = "001",
    include_sensitive: bool = False,
) -> dict[str, Any]:
    """Build a redaction-safe support bundle.

    By default, no raw values are included — only structure hints, hashes,
    bbox, field_path, quality, and evidence linkage are exposed so that
    support teams can investigate parsing and extraction issues without
    seeing customer data.

    Set ``include_sensitive=True`` to include raw values (for internal use
    with explicit opt-in only).

    Returns:
        Support bundle dict ready for JSON serialization.
    """
    # ── Redact field evidence ──
    field_evidence_safe: list[dict[str, Any]] = []
    for item in (evidence_bundle or {}).get("field_evidence") or []:
        raw = str(item.get("value") or item.get("raw_value") or "")
        entry: dict[str, Any] = {
            "field_path": item.get("field_path", "unknown"),
            "value_hash": _hash_value(raw),
            "value_hint": _redact_value(raw) if not include_sensitive else {"raw": raw},
            "page": item.get("page"),
            "bbox": item.get("bbox"),
            "confidence": item.get("confidence"),
            "review": item.get("review", "auto_accepted"),
        }
        if include_sensitive and raw:
            entry["value"] = raw[:500]
        field_evidence_safe.append(entry)

    # ── Redact projection evidence ──
    projection_evidence_safe: list[dict[str, Any]] = []
    for item in (evidence_bundle or {}).get("projection_evidence") or []:
        projection_evidence_safe.append({
            "projection_id": item.get("projection_id", ""),
            "target": item.get("target", ""),
            "source_fact_ids": item.get("source_fact_ids", []),
            "evidence_ids": item.get("evidence_ids", []),
            "projection_policy": item.get("projection_policy", "unknown"),
            "confidence": item.get("confidence"),
            "support_level": item.get("support_level", "unknown"),
            "review": item.get("review", "auto_accepted"),
            "fallback_reason": item.get("fallback_reason"),
        })

    # ── Redact unresolved evidence ──
    unresolved_safe: list[dict[str, Any]] = []
    for item in (evidence_bundle or {}).get("unresolved") or []:
        unresolved_safe.append({
            "field_path": item.get("field_path", "unknown"),
            "reason": item.get("reason", "unresolved"),
            "confidence": item.get("confidence"),
        })

    # ── Ledger summary (safe by construction — no raw values in ledger summary) ──
    ledger_summary_data = (evidence_bundle or {}).get("ledger_summary") or {}

    # ── Quality summary ──
    quality = (evidence_bundle or {}).get("quality") or {}
    quality_safe = {
        "structure_readiness": quality.get("structure_readiness"),
        "text_fidelity": quality.get("text_fidelity"),
        "layout_fidelity": quality.get("layout_fidelity"),
        "audit_fidelity": quality.get("audit_fidelity"),
    }

    # ── Edition metadata (safe by construction) ──
    edition_meta_safe: dict[str, Any] = {}
    for ed_name, payload in (editions or {}).items():
        if not isinstance(payload, dict):
            continue
        meta = payload.get("metadata") or {}
        edition_meta_safe[ed_name] = {
            "support_level": meta.get("support_level", "unknown"),
            "domain_status": meta.get("domain_status", "unknown"),
            "route_type": meta.get("route_type", "unknown"),
            "fallback_reason": meta.get("fallback_reason"),
            "projection_coverage": meta.get("projection_coverage"),
        }

    return {
        "version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "document_id": document_id,
        "task_id": task_id,
        "file_id": file_id,
        "redaction_safe": not include_sensitive,
        "include_sensitive": include_sensitive,
        "ledger_summary": ledger_summary_data,
        "field_evidence": field_evidence_safe,
        "projection_evidence": projection_evidence_safe,
        "unresolved": unresolved_safe,
        "edition_metadata": edition_meta_safe,
        "quality": quality_safe,
        "warnings": list((evidence_bundle or {}).get("warnings") or []),
        "support": {
            "redaction_safe": True,
            "minimal_repro": _build_minimal_repro(result, editions),
            "evidence_linkage": {
                "total_ledger_entries": ledger_summary_data.get("total_entries", 0),
                "bbox_coverage": (
                    ledger_summary_data.get("coverage") or {}
                ).get("bbox", {}).get("ratio", 0.0),
                "source_ref_coverage": (
                    ledger_summary_data.get("coverage") or {}
                ).get("source_refs", {}).get("ratio", 0.0),
                "unresolved_count": len(unresolved_safe),
            },
        },
    }


def is_support_bundle_redaction_safe(bundle: dict[str, Any]) -> bool:
    """Check if a support bundle is redaction-safe.

    Returns True if the bundle was built with ``include_sensitive=False``
    and has the correct metadata.
    """
    return bool(
        bundle.get("redaction_safe")
        and not bundle.get("include_sensitive")
        and bundle.get("support", {}).get("redaction_safe")
    )


__all__ = [
    "build_support_bundle",
    "is_support_bundle_redaction_safe",
]
