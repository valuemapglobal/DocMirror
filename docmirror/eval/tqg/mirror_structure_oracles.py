# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mirror structure oracles — SPE / SSO regression (Phase 5 / ADR-M13-02)."""

from __future__ import annotations

from typing import Any

from docmirror.eval.tqg.report import GateReport


def run_mirror_structure_oracle(
    meta: dict[str, Any],
    spec: dict[str, Any],
    *,
    case_id: str = "",
    track: str = "",
    tier: str = "",
) -> GateReport:
    """Validate ``parser_info.structure`` / metadata SPE fields."""
    report = GateReport(case_id=case_id, track=track, tier=tier)
    base = meta.get("base")
    if base is None:
        report.passed = False
        report.failures.append("mirror_structure: missing base metadata")
        return report

    structure = (base.metadata or {}).get("structure")
    if not isinstance(structure, dict):
        report.passed = False
        report.failures.append("mirror_structure: metadata.structure missing")
        return report

    report.metrics["structure_primary"] = structure.get("primary")
    report.metrics["H_pipe_grid"] = (structure.get("competitors") or {}).get("H_pipe_grid")

    expected_primary = spec.get("primary")
    if expected_primary:
        ok = structure.get("primary") == expected_primary
        report.checks["primary"] = ok
        if not ok:
            report.passed = False
            report.failures.append(
                f"structure.primary expected {expected_primary!r}, got {structure.get('primary')!r}"
            )

    min_pipe = spec.get("min_H_pipe_grid")
    if min_pipe is not None:
        h_pipe = float((structure.get("competitors") or {}).get("H_pipe_grid") or 0)
        ok = h_pipe >= float(min_pipe)
        report.checks["min_H_pipe_grid"] = ok
        report.metrics["H_pipe_grid"] = h_pipe
        if not ok:
            report.passed = False
            report.failures.append(f"H_pipe_grid {h_pipe} < {min_pipe}")

    forbidden_skip = spec.get("forbidden_skip_reasons") or []
    reason = structure.get("table_extraction_skipped_reason")
    for code in forbidden_skip:
        ok = reason != code
        report.checks[f"not_{code}"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"table_extraction_skipped_reason must not be {code!r}")

    require_reason_when_empty = spec.get("require_skip_reason_when_tables_empty")
    if require_reason_when_empty:
        table_count = int(meta.get("table_count") or 0)
        if table_count == 0 and structure.get("table_extraction") != "enrich_only":
            ok = bool(reason)
            report.checks["skip_reason_present"] = ok
            if not ok:
                report.passed = False
                report.failures.append("tables empty but table_extraction_skipped_reason missing")

    expected_extraction = spec.get("table_extraction")
    if expected_extraction:
        ok = structure.get("table_extraction") == expected_extraction
        report.checks["table_extraction"] = ok
        if not ok:
            report.passed = False
            report.failures.append(
                f"table_extraction expected {expected_extraction!r}, "
                f"got {structure.get('table_extraction')!r}"
            )

    return report
