# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
TQG extract-layer oracles — column fidelity and quarantine metadata checks.

Validates logical-table column integrity (header counts, required columns,
trade/time field presence) and extraction-audit metadata emitted in
``perf_breakdown``. Returns ``GateReport`` instances for P2-tier TQG tracks.
"""

from __future__ import annotations

import re
from typing import Any

from docmirror.eval.tqg.report import GateReport
from docmirror.tables.access import primary_export_logical_table


def run_column_fidelity_oracle(
    result: Any,
    spec: dict[str, Any],
    *,
    case_id: str = "",
    track: str = "",
    tier: str = "",
) -> GateReport:
    """P2-4 column integrity on primary logical table."""
    report = GateReport(case_id=case_id, track=track, tier=tier)
    primary = primary_export_logical_table(result)
    if primary is None:
        report.passed = False
        report.failures.append("column_fidelity: no logical tables")
        return report
    headers = [str(h) for h in (primary.headers or [])]
    min_cols = int(spec.get("min_columns") or 8)
    report.checks["header_column_count"] = len(headers) >= min_cols
    if len(headers) < min_cols:
        report.passed = False
        report.failures.append(f"headers {len(headers)} < {min_cols}: {headers!r}")

    trade_headers = spec.get("trade_no_headers") or [spec.get("trade_no_header") or "trade_no", "交易单号", "商户单号"]
    time_headers = spec.get("time_headers") or [spec.get("time_header") or "trade_time", "交易时间", "交易日期", "时间"]

    def _header_index(names: list[str]) -> int | None:
        for i, h in enumerate(headers):
            for name in names:
                if name and name in (h or ""):
                    return i
        return None

    trade_idx = _header_index([str(name) for name in trade_headers])
    time_idx = _header_index([str(name) for name in time_headers])
    report.checks["trade_no_column"] = trade_idx is not None
    report.checks["time_column"] = time_idx is not None
    if trade_idx is None:
        report.passed = False
        report.failures.append(f"trade_no column missing in {headers}")
    if time_idx is None:
        report.passed = False
        report.failures.append(f"time column missing in {headers}")

    eight_col_rows = 0
    trade_no_with_space = 0
    bad_timestamps = 0
    sample_size = len(primary.rows)
    col_ratio_min = float(spec.get("column_ratio_min") or 0.99)
    max_bad_ts_ratio = float(spec.get("max_bad_timestamp_ratio") or 0.01)

    for row in primary.rows:
        cells = [c.text for c in row.cells]
        if len(cells) >= min_cols:
            eight_col_rows += 1
        if trade_idx is not None and trade_idx < len(cells):
            trade_val = (cells[trade_idx] or "").strip()
            if trade_val and re.search(r"\s", trade_val):
                trade_no_with_space += 1
        if time_idx is not None and time_idx < len(cells):
            ts = (cells[time_idx] or "").strip()
            if ts and not re.match(r"\d{4}-\d{2}-\d{2}", ts):
                bad_timestamps += 1

    col_ratio = eight_col_rows / max(sample_size, 1)
    report.metrics["column_ratio"] = col_ratio
    report.metrics["trade_no_whitespace_count"] = trade_no_with_space
    report.metrics["bad_timestamp_ratio"] = bad_timestamps / max(sample_size, 1)

    report.checks["column_ratio"] = col_ratio >= col_ratio_min
    if col_ratio < col_ratio_min:
        report.passed = False
        report.failures.append(f"column_ratio {col_ratio:.3f} < {col_ratio_min}")

    max_trade_ws = int(spec.get("max_trade_no_whitespace") or 0)
    report.checks["trade_no_whitespace"] = trade_no_with_space <= max_trade_ws
    if trade_no_with_space > max_trade_ws:
        report.passed = False
        report.failures.append(f"{trade_no_with_space} trade_no cells contain whitespace")

    bad_ts_ratio = bad_timestamps / max(sample_size, 1)
    report.checks["timestamp_integrity"] = bad_ts_ratio < max_bad_ts_ratio
    if bad_ts_ratio >= max_bad_ts_ratio:
        report.passed = False
        report.failures.append(f"bad timestamp ratio {bad_ts_ratio:.3f} >= {max_bad_ts_ratio}")

    return report


def run_quarantine_metadata_oracle(
    meta: dict[str, Any],
    spec: dict[str, Any],
    *,
    case_id: str = "",
    track: str = "",
    tier: str = "",
) -> GateReport:
    """P3-2 quarantined-table facts on the canonical result."""
    report = GateReport(case_id=case_id, track=track, tier=tier)
    quarantined = meta.get("quarantined") or []
    report.metrics["quarantine_count"] = len(quarantined)
    if spec.get("require_nonempty") and not quarantined:
        report.passed = False
        report.failures.append("quarantine oracle: expected quarantined_tables entries")
        return report

    if not quarantined:
        report.checks["quarantine_present"] = True
        return report

    page = spec.get("page")
    reason = spec.get("reason")
    action = spec.get("action")
    match = None
    if page is not None:
        match = next((q for q in quarantined if q.get("page") == int(page)), None)
        report.checks["quarantine_page"] = match is not None
        if match is None:
            report.passed = False
            report.failures.append(f"quarantine page {page} not found in {quarantined!r}")
    else:
        match = quarantined[0]

    if match and reason is not None:
        ok = match.get("reason") == reason
        report.checks["quarantine_reason"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"quarantine reason expected {reason!r}, got {match.get('reason')!r}")

    if match and action is not None:
        ok = match.get("action") == action
        report.checks["quarantine_action"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"quarantine action expected {action!r}, got {match.get('action')!r}")

    return report


def run_text_snapshot_oracle(
    meta: dict[str, Any],
    spec: dict[str, Any],
    *,
    case_id: str = "",
    track: str = "",
    tier: str = "",
) -> GateReport:
    """§9.2 normalized canonical text snapshot hash."""
    import hashlib

    report = GateReport(case_id=case_id, track=track, tier=tier)
    result = meta.get("result") or meta.get("parse_result")
    if result is None:
        report.passed = False
        report.failures.append("text_snapshot: missing ParseResult")
        return report

    text_lines = sorted(str(block.content).strip() for page in result.pages for block in page.texts if block.content)
    min_lines = int(spec.get("min_text_lines") or 1)
    report.checks["min_text_lines"] = len(text_lines) >= min_lines
    if len(text_lines) < min_lines:
        report.passed = False
        report.failures.append(f"text lines {len(text_lines)} < {min_lines}")

    joined = "\n".join(text_lines)
    for needle in spec.get("contains") or []:
        ok = str(needle) in joined
        key = f"contains_{str(needle)[:12]}"
        report.checks[key] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"text_snapshot missing substring: {needle!r}")

    expected = spec.get("expected_sha256")
    if expected:
        digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
        report.metrics["text_snapshot_sha256"] = digest
        ok = digest == expected
        report.checks["text_snapshot_sha256"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"text_snapshot sha256 expected {expected}, got {digest}")

    return report
