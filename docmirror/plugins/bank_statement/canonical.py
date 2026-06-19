# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Canonical transaction record builders and style metadata for bank statements.

Defines ``CANONICAL_FIELDS``, ``StyleMeta`` (style_id, confidence, parser chain),
and helpers to normalize raw style-parser output into edition-ready record dicts with
``raw`` and ``normalized`` sub-objects.

Pipeline role: ``style_registry`` and individual style parsers call these builders
before ``community_plugin`` serializes DEC output.

Key exports: ``CANONICAL_FIELDS``, ``StyleMeta``, ``build_style_meta``,
``ensure_canonical_normalized``, ``records_from_raw_transactions``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CANONICAL_FIELDS = (
    "date",
    "timestamp",
    "summary",
    "amount",
    "amount_cny",
    "direction",
    "balance",
    "counter_party",
    "counter_account",
    "reference",
)


@dataclass
class StyleMeta:
    style_id: str
    style_confidence: float
    parser_chain: list[str] = field(default_factory=list)
    institution_hint: str | None = None
    secondary_styles: list[str] = field(default_factory=list)
    reconstruction_source: str = ""
    expected_primary_rows: int = 0
    extracted_rows: int = 0
    coverage_ratio: float = 0.0
    institution_authority: str = ""
    pipe_parse_failed: bool = False
    canonical_expected: int = 0
    canonical_extracted: int = 0
    canonical_ratio: float = 0.0
    extract_status: str = "success"
    blo_tables_parsed: int = 0
    blo_tables_skipped: int = 0

    def to_properties(self) -> dict[str, Any]:
        return {
            "style_id": self.style_id,
            "style_confidence": round(self.style_confidence, 4),
            "parser_chain": list(self.parser_chain),
            "institution_hint": self.institution_hint or "",
            "secondary_styles": list(self.secondary_styles),
            "reconstruction_source": self.reconstruction_source,
            "expected_primary_rows": self.expected_primary_rows,
            "extracted_rows": self.extracted_rows,
            "coverage_ratio": round(self.coverage_ratio, 4),
            "institution_authority": self.institution_authority,
            "pipe_parse_failed": self.pipe_parse_failed,
            "canonical_expected": self.canonical_expected,
            "canonical_extracted": self.canonical_extracted,
            "canonical_ratio": round(self.canonical_ratio, 4),
            "extract_status": self.extract_status,
            "blo_tables_parsed": self.blo_tables_parsed,
            "blo_tables_skipped": self.blo_tables_skipped,
        }


def build_style_meta(
    detection: Any,
    *,
    reconstruction: Any = None,
    record_count: int = 0,
    parse_result: Any = None,
    records: list[dict[str, Any]] | None = None,
    blo_meta: Any = None,
) -> StyleMeta:
    expected = 0
    source = ""
    pipe_failed = False
    if reconstruction is not None:
        expected = getattr(reconstruction, "expected_primary_rows", 0) or 0
        source = getattr(reconstruction, "source", "") or ""
        pipe_failed = bool(getattr(reconstruction, "pipe_parse_failed", False))

    from docmirror.plugins.bank_statement.canonical_quality import (
        audit_cqf,
        canonical_expected_from_parse_result,
    )

    canonical_expected = canonical_expected_from_parse_result(parse_result)
    if canonical_expected > 0:
        expected = canonical_expected
    elif parse_result is not None and source in ("mirror_table", ""):
        from docmirror.core.analyze.spe_consumer import mirror_expected_primary_rows

        mirror_expected = mirror_expected_primary_rows(parse_result)
        if mirror_expected > 0:
            expected = mirror_expected

    cqf = audit_cqf(records or [], canonical_expected=expected)
    coverage = cqf.coverage_ratio
    if records is None and expected > 0:
        coverage = min(record_count / expected, 1.0) if record_count > 0 else 0.0
    if expected <= 0 and record_count > 0:
        coverage = 1.0

    blo_parsed = 0
    blo_skipped = 0
    if blo_meta is not None:
        blo_parsed = int(getattr(blo_meta, "tables_parsed", 0) or 0)
        blo_skipped = int(getattr(blo_meta, "tables_skipped", 0) or 0)

    return StyleMeta(
        style_id=detection.primary_style,
        style_confidence=detection.confidence,
        parser_chain=list(detection.parser_chain),
        institution_hint=detection.institution_hint,
        secondary_styles=list(detection.secondary_styles),
        reconstruction_source=source,
        expected_primary_rows=expected,
        extracted_rows=record_count,
        coverage_ratio=coverage,
        institution_authority=getattr(detection, "institution_authority", "") or "",
        pipe_parse_failed=pipe_failed,
        canonical_expected=cqf.canonical_expected,
        canonical_extracted=cqf.canonical_extracted,
        canonical_ratio=cqf.canonical_ratio,
        extract_status=cqf.extract_status,
        blo_tables_parsed=blo_parsed,
        blo_tables_skipped=blo_skipped,
    )


def dedupe_transaction_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedupe by (date, amount, balance, counter_party) — ADR-BS-05."""
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for rec in records:
        norm = rec.get("normalized") or {}
        balance = norm.get("balance")
        try:
            balance_key = float(balance) if balance not in (None, "") else None
        except (TypeError, ValueError):
            balance_key = balance
        try:
            amount_key = float(norm.get("amount") or 0)
        except (TypeError, ValueError):
            amount_key = norm.get("amount")
        key = (
            str(norm.get("date") or ""),
            amount_key,
            balance_key,
            str(norm.get("counter_party") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(rec))
    for idx, rec in enumerate(out, start=1):
        rec["row_index"] = idx
    return out


def ensure_canonical_normalized(normalized: dict[str, Any], standard_fields: list[str]) -> dict[str, Any]:
    out = dict(normalized)
    for fld in standard_fields:
        if fld not in out:
            out[fld] = "" if fld not in ("amount", "amount_cny", "balance") else None
    if out.get("amount") is None:
        out["amount"] = 0.0
    if out.get("amount_cny") is None:
        out["amount_cny"] = out.get("amount")
    if "direction" not in out:
        out["direction"] = "other"
    return out


def records_from_raw_transactions(
    transactions: list[dict[str, str]],
    *,
    normalize_fn,
    style_id: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx, raw_txn in enumerate(transactions, start=1):
        raw = dict(raw_txn)
        raw.setdefault("_style_id", style_id)
        normalized = normalize_fn(raw_txn)
        records.append({
            "row_index": idx,
            "raw": raw,
            "normalized": normalized,
        })
    return records
