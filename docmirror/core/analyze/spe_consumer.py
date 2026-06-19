# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SPE consumer helpers — Plugin / LTRO reads Mirror structure provenance (ADR-M13-04)."""

from __future__ import annotations

from typing import Any

from docmirror.core.analyze.sso_config import pipe_grid_veto_threshold


def read_structure_spe(parse_result: Any) -> dict[str, Any] | None:
    """Return ``parser_info.structure`` when present."""
    info = getattr(parse_result, "parser_info", None)
    spe = getattr(info, "structure", None) if info else None
    return spe if isinstance(spe, dict) else None


def pipe_grid_score(spe: dict[str, Any] | None) -> float:
    if not spe:
        return 0.0
    return float((spe.get("competitors") or {}).get("H_pipe_grid") or 0.0)


def should_force_ltro(
    *,
    mirror_tables: list,
    full_text: str,
    structure_spe: dict[str, Any] | None,
) -> bool:
    """True when Mirror tables empty but SPE/text indicate pipe ledger reconstruction."""
    if mirror_tables:
        return False
    if not structure_spe:
        return False
    if should_block_pipe_ltro(structure_spe):
        return False
    reason = structure_spe.get("table_extraction_skipped_reason")
    if reason == "route_section_dominant_mismatch":
        return True
    h_pipe = pipe_grid_score(structure_spe)
    threshold = pipe_grid_veto_threshold()
    mode = structure_spe.get("table_extraction")
    if h_pipe >= threshold and mode in ("skipped", "full", "enrich_only"):
        return True
    if mode == "full" and h_pipe >= 0.5:
        return True
    return False


def should_block_pipe_ltro(structure_spe: dict[str, Any] | None) -> bool:
    """True when SSO/SPE clearly routed away from pipe ledger (gate pipe LTRO)."""
    if not structure_spe:
        return False
    if structure_spe.get("table_extraction_skipped_reason") == "route_section_dominant_mismatch":
        return False
    primary = structure_spe.get("primary")
    mode = structure_spe.get("table_extraction")
    reason = structure_spe.get("table_extraction_skipped_reason")
    h_pipe = pipe_grid_score(structure_spe)
    threshold = pipe_grid_veto_threshold()
    if primary == "section_led" and mode == "skipped" and reason == "route_section_dominant":
        return h_pipe < threshold
    if primary == "prose_led" and mode == "skipped" and reason in (
        "route_section_dominant",
        "no_tabular_signal",
    ):
        return h_pipe < 0.3
    return False


def spe_ltro_warnings(structure_spe: dict[str, Any] | None, reconstruction_source: str) -> list[str]:
    """Cross-audit SPE vs Plugin reconstruction_source."""
    if not structure_spe:
        return []
    warnings: list[str] = []
    reason = structure_spe.get("table_extraction_skipped_reason")
    h_pipe = pipe_grid_score(structure_spe)
    if reason == "route_section_dominant_mismatch":
        warnings.append("spe:mismatch_section_route_with_pipe_grid")
    if h_pipe >= pipe_grid_veto_threshold() and reconstruction_source == "none":
        warnings.append("spe:pipe_grid_high_but_ltro_none")
    if structure_spe.get("table_extraction") == "full" and reconstruction_source == "pipe_text":
        warnings.append("spe:mirror_table_extraction_full_used_ltro_fallback")
    warnings.extend(spe_ltqg_warnings(structure_spe))
    return warnings


def read_ltqg_summary(
    structure_spe: dict[str, Any] | None,
    parse_result: Any = None,
) -> dict[str, Any]:
    """Mirror LTQG summary from SPE and/or ``ParseResult.logical_tables``."""
    if structure_spe and structure_spe.get("ltqg_enabled"):
        out = {
            "enabled": True,
            "passed_tables": int(structure_spe.get("ltqg_passed_tables") or 0),
            "skipped_tables": int(structure_spe.get("ltqg_skipped_tables") or 0),
            "expected_data_rows": int(structure_spe.get("ltqg_expected_data_rows") or 0),
        }
        export_n = structure_spe.get("ltqg_export_logical_tables")
        if export_n is not None:
            out["export_logical_tables"] = int(export_n)
        legacy = int(structure_spe.get("ltqg_legacy_max_rows") or 0)
        if legacy:
            out["legacy_max_rows"] = legacy
        skipped_ids = structure_spe.get("ltqg_skipped_logical_ids")
        if skipped_ids:
            out["skipped_logical_ids"] = list(skipped_ids)
        return out

    logical_tables = getattr(parse_result, "logical_tables", None) if parse_result else None
    if not logical_tables:
        return {"enabled": False, "expected_data_rows": 0, "passed_tables": 0, "skipped_tables": 0}

    from docmirror.core.table.compose.ledger_quality import sum_passed_data_row_estimates

    has_scores = any(
        getattr(lt, "quality_passed", True) is False or getattr(lt, "quality_skip_reason", None)
        for lt in logical_tables
    )
    if not has_scores and not (structure_spe or {}).get("ltqg_enabled"):
        from docmirror.core.table.access import primary_export_logical_table

        primary = primary_export_logical_table(parse_result) if parse_result else None
        primary_rows = (
            int(
                getattr(primary, "data_row_estimate", 0)
                or getattr(primary, "row_count", 0)
                or 0
            )
            if primary is not None
            else max((int(getattr(lt, "row_count", 0) or 0) for lt in logical_tables), default=0)
        )
        return {
            "enabled": False,
            "expected_data_rows": primary_rows,
            "passed_tables": len(logical_tables),
            "skipped_tables": 0,
        }

    skipped_ids = [
        str(getattr(lt, "logical_id", None) or getattr(lt, "table_id", ""))
        for lt in logical_tables
        if not getattr(lt, "quality_passed", True)
    ]
    passed_n = sum(1 for lt in logical_tables if getattr(lt, "quality_passed", True))
    return {
        "enabled": True,
        "passed_tables": passed_n,
        "skipped_tables": len(skipped_ids),
        "skipped_logical_ids": skipped_ids,
        "expected_data_rows": sum_passed_data_row_estimates(logical_tables),
    }


def mirror_expected_primary_rows(
    parse_result: Any,
    structure_spe: dict[str, Any] | None = None,
) -> int:
    """Mirror-side expected primary row count (ADR-BS-07 SSOT for Plugin consumers)."""
    spe = structure_spe if structure_spe is not None else read_structure_spe(parse_result)
    summary = read_ltqg_summary(spe, parse_result)
    if summary.get("enabled"):
        return int(summary.get("expected_data_rows") or 0)

    logical_tables = getattr(parse_result, "logical_tables", None) if parse_result else None
    if logical_tables:
        from docmirror.core.table.access import primary_export_logical_table

        primary = primary_export_logical_table(parse_result)
        if primary is not None:
            return int(
                getattr(primary, "data_row_estimate", 0)
                or getattr(primary, "row_count", 0)
                or 0
            )
        return 0

    if spe and spe.get("logical_table_count"):
        return 0
    return 0


def spe_ltqg_warnings(structure_spe: dict[str, Any] | None) -> list[str]:
    """Audit warnings when LTQG skipped tables or expected rows diverge from legacy max."""
    if not structure_spe or not structure_spe.get("ltqg_enabled"):
        return []
    warnings: list[str] = []
    skipped = int(structure_spe.get("ltqg_skipped_tables") or 0)
    if skipped > 0:
        warnings.append(f"ltqg:skipped_tables:{skipped}")
    expected = int(structure_spe.get("ltqg_expected_data_rows") or 0)
    legacy_max = int(structure_spe.get("ltqg_legacy_max_rows") or 0)
    if legacy_max > expected and legacy_max > 0:
        warnings.append(f"ltqg:expected_below_legacy_max:{expected}/{legacy_max}")
    return warnings


def mirror_api_meta_fields(parse_result: Any) -> dict[str, Any]:
    """Mirror Core SSOT fields merged into ``ParseResult.to_api_dict`` meta."""
    spe = read_structure_spe(parse_result)
    ds = dict(getattr(getattr(parse_result, "entities", None), "domain_specific", None) or {})
    out: dict[str, Any] = {}

    if isinstance(spe, dict):
        if spe.get("physical_table_count") is not None:
            out["physical_table_count"] = int(spe["physical_table_count"])
        if spe.get("dual_view") is not None:
            out["dual_view"] = bool(spe["dual_view"])
        export_n = spe.get("ltqg_export_logical_tables")
        if export_n is None:
            export_n = spe.get("logical_table_count")
        if export_n is not None:
            out["logical_table_count"] = int(export_n)

    ltqg = read_ltqg_summary(spe, parse_result)
    if ltqg.get("enabled"):
        block: dict[str, Any] = {
            "enabled": True,
            "expected_data_rows": int(ltqg.get("expected_data_rows") or 0),
            "passed_tables": int(ltqg.get("passed_tables") or 0),
            "skipped_tables": int(ltqg.get("skipped_tables") or 0),
        }
        export_n = ltqg.get("export_logical_tables")
        if export_n is not None:
            block["export_logical_tables"] = int(export_n)
        legacy = int(ltqg.get("legacy_max_rows") or 0)
        if legacy:
            block["legacy_max_rows"] = legacy
        skipped_ids = ltqg.get("skipped_logical_ids")
        if skipped_ids:
            block["skipped_logical_ids"] = list(skipped_ids)
        out["ltqg"] = block

    expected = mirror_expected_primary_rows(parse_result, spe)
    if expected > 0:
        out["mirror_expected_data_rows"] = expected

    plugin_type = ds.get("plugin_document_type")
    if plugin_type:
        out["plugin_document_type"] = plugin_type

    q_phys = int((spe or {}).get("quarantined_physical_count") or ds.get("mirror_quarantined_physical_count") or 0)
    q_log = int((spe or {}).get("quarantined_logical_count") or ds.get("mirror_quarantined_logical_count") or 0)
    if q_phys:
        out["quarantined_physical_count"] = q_phys
    if q_log:
        out["quarantined_logical_count"] = q_log
    if q_phys or q_log:
        out["quarantine"] = {"physical_count": q_phys, "logical_count": q_log}

    return out


def mirror_quarantine_annex_fields(
    parse_result: Any,
    *,
    mirror_level: str = "standard",
) -> dict[str, Any]:
    """Full quarantine lists for debug / forensic API export."""
    from docmirror.core.debug.artifact import is_debug_mode

    if mirror_level != "forensic" and not is_debug_mode():
        return {}

    spe = read_structure_spe(parse_result) or {}
    annex: dict[str, Any] = {}
    physical = spe.get("quarantined_physical_tables")
    logical = spe.get("quarantined_logical_tables_annex")
    if physical:
        annex["quarantined_tables"] = list(physical)
    if logical:
        annex["quarantined_logical_tables"] = list(logical)
    return annex
