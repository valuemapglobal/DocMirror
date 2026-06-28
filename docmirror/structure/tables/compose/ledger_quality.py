# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Ledger Table Quality Gate (LTQG) — Mirror-side logical table quality scoring.

Scores composed ``LogicalTable`` instances using document-agnostic structural
signals (header vocabulary, column stability, data-row patterns, fragment ratio).
Bad tables are marked ``quality_passed=False`` so Plugin expected-row denominators
are not polluted (ADR-BS-07 / design doc Phase 1).

Enabled only for bank-statement layout profiles (G-BS-01); wechat/alipay borderless
profiles are excluded.
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from docmirror.structure.profile.registry import is_borderless_ledger_profile
from docmirror.structure.utils.vocabulary import _is_data_row, _score_header_by_vocabulary
from docmirror.models.entities.parse_result import LogicalTable, TableRow

LTQG_PASS_THRESHOLD = 0.55
_HEADER_LOOKAHEAD = 8
_FOOTER_MARKERS = re.compile(r"合计|小计|本页|总计|Total", re.I)


@dataclass(frozen=True)
class LedgerTableQuality:
    score: float
    passed: bool
    skip_reason: str | None
    data_row_estimate: int
    signals: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class LTQGSummary:
    enabled: bool
    passed_tables: int
    skipped_tables: int
    expected_data_rows: int
    skipped_logical_ids: tuple[str, ...] = ()
    legacy_max_rows: int = 0
    export_logical_tables: int = 0

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "enabled": self.enabled,
            "passed_tables": self.passed_tables,
            "skipped_tables": self.skipped_tables,
            "expected_data_rows": self.expected_data_rows,
        }
        if self.skipped_logical_ids:
            out["skipped_logical_ids"] = list(self.skipped_logical_ids)
        if self.legacy_max_rows:
            out["legacy_max_rows"] = self.legacy_max_rows
        if self.export_logical_tables:
            out["export_logical_tables"] = self.export_logical_tables
        return out


def exported_data_row_estimate(lt: LogicalTable) -> int:
    """Rows counted toward Mirror expected denominator (0 when LTQG failed)."""
    if not getattr(lt, "quality_passed", True):
        return 0
    return int(getattr(lt, "data_row_estimate", 0) or getattr(lt, "row_count", 0) or 0)


def partition_export_logical_tables(
    logical_tables: list[LogicalTable],
) -> tuple[list[LogicalTable], list[LogicalTable]]:
    """Split exportable vs LTQG-failed logical tables (ADR-BS-07 export contract)."""
    passed = [lt for lt in logical_tables if getattr(lt, "quality_passed", True)]
    skipped = [lt for lt in logical_tables if not getattr(lt, "quality_passed", True)]
    return passed, skipped


def _legacy_max_row_count(
    logical_tables: list[LogicalTable],
    quarantined_tables: list[dict[str, Any]] | None = None,
) -> int:
    """Pre-LTQG-export max row signal — includes physical quarantine tables."""
    legacy = max((int(lt.row_count or 0) for lt in logical_tables), default=0)
    if quarantined_tables:
        legacy = max(
            legacy,
            max((int(q.get("row_count") or 0) for q in quarantined_tables), default=0),
        )
    return legacy


def finalize_logical_tables_for_export(
    logical_tables: list[LogicalTable],
    *,
    profile: Any | None = None,
    quarantined_pages: set[int] | None = None,
    quarantined_tables: list[dict[str, Any]] | None = None,
) -> tuple[list[LogicalTable], list[LogicalTable], LTQGSummary]:
    """Apply LTQG and partition export vs quarantined logical tables (Mirror SSOT)."""
    scored, summary = apply_ltqg(
        logical_tables,
        profile=profile,
        quarantined_pages=quarantined_pages,
        quarantined_tables=quarantined_tables,
    )
    export, skipped = partition_export_logical_tables(scored)
    if summary.enabled:
        summary = LTQGSummary(
            enabled=True,
            passed_tables=summary.passed_tables,
            skipped_tables=summary.skipped_tables,
            expected_data_rows=summary.expected_data_rows,
            skipped_logical_ids=summary.skipped_logical_ids,
            legacy_max_rows=summary.legacy_max_rows,
            export_logical_tables=len(export),
        )
    return export, skipped, summary


def should_enable_ltqg(profile: Any | None) -> bool:
    """G-BS-01: LTQG only for bank-statement ledger profiles."""
    if profile is None:
        return False
    hint = getattr(profile, "document_type_hint", None) or ""
    if hint == "bank_statement":
        return True
    pid = getattr(profile, "profile_id", "") or ""
    if pid == "borderless_ledger_bank":
        return True
    if is_borderless_ledger_profile(profile) and hint not in ("wechat_payment", "alipay_payment"):
        if pid.endswith("_bank") or "bank" in pid:
            return True
    return False


def _normalize_header_cell(text: str) -> str:
    cell = unicodedata.normalize("NFKC", str(text or "").strip())
    return re.sub(r"[\s\n\r\t\u3000]", "", cell).replace("\u00a0", "")


def _row_texts(row: TableRow | list[str]) -> list[str]:
    if isinstance(row, TableRow):
        return [str(c.text or "") for c in row.cells]
    return [str(c or "") for c in row]


def _header_match_count(lt: LogicalTable) -> int:
    candidates: list[list[str]] = []
    if lt.headers:
        candidates.append([str(h) for h in lt.headers])
    for row in lt.rows[:_HEADER_LOOKAHEAD]:
        candidates.append(_row_texts(row))
    best = 0
    for row in candidates:
        if not row:
            continue
        best = max(best, _score_header_by_vocabulary(row, categories=["BANK_STATEMENT"]))
    return best


def _col_count_stable(rows: list[TableRow]) -> tuple[bool, float]:
    counts = [len(r.cells) for r in rows if r.cells]
    if len(counts) < 2:
        return True, 1.0
    median = statistics.median(counts)
    if median <= 0:
        return False, 0.0
    deviations = [abs(c - median) / median for c in counts]
    stable_ratio = sum(1 for d in deviations if d <= 0.25) / len(deviations)
    return stable_ratio >= 0.85, stable_ratio


def _data_row_pattern_ratio(rows: list[TableRow]) -> float:
    if not rows:
        return 0.0
    hits = 0
    for row in rows:
        texts = _row_texts(row)
        joined = " ".join(texts)
        if _FOOTER_MARKERS.search(joined):
            continue
        if _is_data_row(texts):
            hits += 1
    return hits / max(len(rows), 1)


def _fragment_ratio(lt: LogicalTable) -> float:
    cells: list[str] = []
    for h in lt.headers or []:
        cells.append(str(h))
    for row in lt.rows:
        cells.extend(_row_texts(row))
    if not cells:
        return 1.0
    empty = sum(1 for c in cells if not str(c).strip())
    short = sum(1 for c in cells if 0 < len(str(c).strip()) <= 1)
    normalized_headers = [_normalize_header_cell(h) for h in (lt.headers or [])]
    empty_headers = sum(1 for h in normalized_headers if not h)
    frag = (empty + short * 0.5 + empty_headers * 2) / max(len(cells), 1)
    return min(1.0, frag)


def estimate_data_rows(rows: list[TableRow]) -> int:
    count = 0
    for row in rows:
        texts = _row_texts(row)
        joined = " ".join(texts)
        if _FOOTER_MARKERS.search(joined):
            continue
        if _is_data_row(texts):
            count += 1
    return count


def assess_logical_table(
    lt: LogicalTable,
    *,
    quarantined_pages: set[int] | None = None,
) -> LedgerTableQuality:
    """Score one logical table; pure structural signals (no bank-specific rules)."""
    rows = lt.rows or []
    header_match = _header_match_count(lt)
    col_stable, col_stable_ratio = _col_count_stable(rows)
    data_ratio = _data_row_pattern_ratio(rows)
    fragment = _fragment_ratio(lt)

    if quarantined_pages and lt.source_pages:
        if all(p in quarantined_pages for p in lt.source_pages):
            return LedgerTableQuality(
                score=0.0,
                passed=False,
                skip_reason="merge_quarantine",
                data_row_estimate=0,
                signals={
                    "header_match": float(header_match),
                    "col_stable_ratio": col_stable_ratio,
                    "data_row_ratio": data_ratio,
                    "fragment_ratio": fragment,
                },
            )

    score = 0.0
    if header_match >= 3:
        score += 0.35
    elif header_match >= 2:
        score += 0.20
    elif header_match >= 1:
        score += 0.08

    if col_stable:
        score += 0.25
    else:
        score += 0.05

    if data_ratio >= 0.5:
        score += 0.30
    elif data_ratio >= 0.3:
        score += 0.18
    elif data_ratio >= 0.15:
        score += 0.08

    score -= fragment * 0.45
    score = max(0.0, min(1.0, score))

    passed = score >= LTQG_PASS_THRESHOLD and header_match >= 2 and data_ratio >= 0.20 and fragment < 0.55

    skip_reason: str | None = None
    if not passed:
        if fragment >= 0.55:
            skip_reason = "fragment_table"
        elif header_match < 2:
            skip_reason = "header_missing"
        elif not col_stable:
            skip_reason = "col_unstable"
        else:
            skip_reason = "low_quality_score"

    data_row_estimate = estimate_data_rows(rows) if passed else 0

    return LedgerTableQuality(
        score=round(score, 4),
        passed=passed,
        skip_reason=skip_reason,
        data_row_estimate=data_row_estimate,
        signals={
            "header_match": float(header_match),
            "col_stable_ratio": round(col_stable_ratio, 4),
            "data_row_ratio": round(data_ratio, 4),
            "fragment_ratio": round(fragment, 4),
        },
    )


def apply_quality_to_logical_table(
    lt: LogicalTable,
    quality: LedgerTableQuality,
) -> LogicalTable:
    """Return a copy of ``lt`` with quality fields populated."""
    data = lt.model_dump()
    data.update(
        {
            "quality_score": quality.score,
            "quality_passed": quality.passed,
            "quality_skip_reason": quality.skip_reason,
            "data_row_estimate": quality.data_row_estimate,
            "quality_signals": quality.signals,
        }
    )
    return LogicalTable(**data)


def apply_ltqg(
    logical_tables: list[LogicalTable],
    *,
    profile: Any | None = None,
    quarantined_pages: set[int] | None = None,
    quarantined_tables: list[dict[str, Any]] | None = None,
) -> tuple[list[LogicalTable], LTQGSummary]:
    """Assess all logical tables when LTQG is enabled for ``profile``."""
    if not logical_tables or not should_enable_ltqg(profile):
        expected = sum(lt.row_count for lt in logical_tables)
        return logical_tables, LTQGSummary(
            enabled=False,
            passed_tables=len(logical_tables),
            skipped_tables=0,
            expected_data_rows=expected,
            legacy_max_rows=_legacy_max_row_count(logical_tables, quarantined_tables),
        )

    q_pages = quarantined_pages or set()
    out: list[LogicalTable] = []
    passed_n = 0
    skipped_n = 0
    skipped_ids: list[str] = []
    expected = 0
    legacy_max = _legacy_max_row_count(logical_tables, quarantined_tables)
    for lt in logical_tables:
        quality = assess_logical_table(lt, quarantined_pages=q_pages)
        out.append(apply_quality_to_logical_table(lt, quality))
        if quality.passed:
            passed_n += 1
            expected += quality.data_row_estimate
        else:
            skipped_n += 1
            skipped_ids.append(str(lt.logical_id or lt.table_id or ""))

    return out, LTQGSummary(
        enabled=True,
        passed_tables=passed_n,
        skipped_tables=skipped_n,
        expected_data_rows=expected,
        skipped_logical_ids=tuple(x for x in skipped_ids if x),
        legacy_max_rows=legacy_max,
    )


def sum_passed_data_row_estimates(logical_tables: list[LogicalTable]) -> int:
    """Mirror-side expected primary rows (ADR-BS-07)."""
    if not logical_tables:
        return 0
    if any(getattr(lt, "quality_passed", True) is False for lt in logical_tables):
        return sum(
            int(getattr(lt, "data_row_estimate", 0) or 0)
            for lt in logical_tables
            if getattr(lt, "quality_passed", True)
        )
    return sum(int(lt.row_count or 0) for lt in logical_tables)


__all__ = [
    "LTQG_PASS_THRESHOLD",
    "LedgerTableQuality",
    "LTQGSummary",
    "apply_ltqg",
    "apply_quality_to_logical_table",
    "assess_logical_table",
    "estimate_data_rows",
    "exported_data_row_estimate",
    "finalize_logical_tables_for_export",
    "partition_export_logical_tables",
    "should_enable_ltqg",
    "sum_passed_data_row_estimates",
]
