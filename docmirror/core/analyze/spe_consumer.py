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
    return warnings
