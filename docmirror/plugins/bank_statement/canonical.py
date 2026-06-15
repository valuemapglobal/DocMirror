# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Canonical transaction builders and style metadata."""

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

    def to_properties(self) -> dict[str, Any]:
        return {
            "style_id": self.style_id,
            "style_confidence": round(self.style_confidence, 4),
            "parser_chain": list(self.parser_chain),
            "institution_hint": self.institution_hint or "",
            "secondary_styles": list(self.secondary_styles),
        }


def build_style_meta(detection: Any) -> StyleMeta:
    return StyleMeta(
        style_id=detection.primary_style,
        style_confidence=detection.confidence,
        parser_chain=list(detection.parser_chain),
        institution_hint=detection.institution_hint,
        secondary_styles=list(detection.secondary_styles),
    )


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
