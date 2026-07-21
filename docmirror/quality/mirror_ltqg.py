# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Mirror LTQG attachment — sync SPE / domain_specific after ParseResult assembly.

Canonical assembly calls ``attach_mirror_ltqg`` so Plugin and API consumers can read
``mirror_expected_data_rows`` without re-running LTQG.
"""

from __future__ import annotations

from typing import Any

from docmirror.evidence.spe_consumer import mirror_expected_primary_rows, read_ltqg_summary


def attach_mirror_ltqg(parse_result: Any, base_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge LTQG into ``parser_info.structure`` and ``entities.domain_specific``."""
    meta = base_metadata or {}
    structure = dict(
        getattr(getattr(parse_result, "parser_info", None), "structure", None) or meta.get("structure") or {}
    )

    meta_ltqg = meta.get("ltqg")
    if isinstance(meta_ltqg, dict) and meta_ltqg.get("enabled") and not structure.get("ltqg_enabled"):
        from docmirror.evidence.structure_provenance import apply_logical_tables_spe

        logical_count = len(getattr(parse_result, "logical_tables", None) or [])
        structure = apply_logical_tables_spe(
            structure,
            logical_table_count=logical_count or None,
            ltqg_summary=meta_ltqg,
        )

    quarantined_physical = meta.get("quarantined_tables") or []
    quarantined_logical = meta.get("quarantined_logical_tables") or []
    from docmirror.runtime.debug_artifact import is_debug_mode

    if quarantined_physical:
        structure["quarantined_physical_count"] = len(quarantined_physical)
        if is_debug_mode():
            structure["quarantined_physical_tables"] = list(quarantined_physical)
    if quarantined_logical:
        structure["quarantined_logical_count"] = len(quarantined_logical)
        if is_debug_mode():
            structure["quarantined_logical_tables_annex"] = list(quarantined_logical)
    if meta.get("dual_view") is not None:
        structure["dual_view"] = bool(meta["dual_view"])
    elif getattr(parse_result, "logical_tables", None):
        structure["dual_view"] = True

    summary = read_ltqg_summary(structure if structure else None, parse_result)
    expected = mirror_expected_primary_rows(parse_result, structure if structure else None)

    if structure:
        parse_result.parser_info.structure = structure

    if summary.get("enabled"):
        ds = dict(getattr(parse_result.entities, "domain_specific", None) or {})
        ds["mirror_ltqg_enabled"] = True
        ds["mirror_expected_data_rows"] = expected
        ds["mirror_ltqg_passed_tables"] = int(summary.get("passed_tables") or 0)
        ds["mirror_ltqg_skipped_tables"] = int(summary.get("skipped_tables") or 0)
        skipped_ids = summary.get("skipped_logical_ids")
        if skipped_ids:
            ds["mirror_ltqg_skipped_logical_ids"] = list(skipped_ids)
        raw = int(structure.get("ltqg_raw_max_rows") or 0) if structure else 0
        if raw:
            ds["mirror_ltqg_raw_max_rows"] = raw
        export_n = int(structure.get("ltqg_export_logical_tables") or 0)
        if export_n:
            ds["mirror_ltqg_export_tables"] = export_n
        if quarantined_physical:
            ds["mirror_quarantined_physical_count"] = len(quarantined_physical)
        if quarantined_logical:
            ds["mirror_quarantined_logical_count"] = len(quarantined_logical)
        parse_result.entities.domain_specific = ds

    return summary


__all__ = ["attach_mirror_ltqg"]
