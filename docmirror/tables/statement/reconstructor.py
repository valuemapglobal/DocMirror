"""Financial statement structure enrichment."""

from __future__ import annotations

from typing import Any

from docmirror.tables.statement.column_groups import build_column_groups
from docmirror.tables.statement.header_bands import build_header_bands
from docmirror.tables.statement.row_hierarchy import build_account_rows
from docmirror.tables.statement.rules import build_statement_rules

_STATEMENT_TYPES = {
    "资产负债表": "balance_sheet",
    "利润表": "income_statement",
    "现金流量表": "cash_flow_statement",
    "所有者权益变动表": "owners_equity_changes",
}


def build_statement_structure(block: Any, *, source_text: str = "") -> dict[str, Any]:
    grid = block.content.get("grid") if isinstance(getattr(block, "content", None), dict) else None
    if not isinstance(grid, dict):
        return _empty_structure(source_text, reason="missing_grid")

    columns = [col for col in grid.get("columns", []) or [] if isinstance(col, dict)]
    rows = [row for row in grid.get("rows", []) or [] if isinstance(row, dict)]
    cells = [cell for cell in grid.get("cells", []) or [] if isinstance(cell, dict)]
    statement_type = _statement_type(source_text, columns, cells)
    header_bands = build_header_bands(columns, rows, cells)
    column_groups = build_column_groups(
        columns,
        header_bands,
        source_text=source_text,
        statement_type=statement_type,
    )
    account_rows = build_account_rows(rows, cells)
    rules = build_statement_rules(account_rows)
    confidence = _confidence(header_bands, column_groups, account_rows)
    review_reasons = []
    if not header_bands:
        review_reasons.append("missing_header_bands")
    if statement_type == "unknown":
        review_reasons.append("unknown_statement_type")
    if statement_type == "owners_equity_changes" and not column_groups:
        review_reasons.append("missing_owner_equity_column_groups")
    if statement_type == "owners_equity_changes" and not rules:
        review_reasons.append("missing_owner_equity_roll_forward_rule")
    for rule in rules:
        validation = rule.get("validation") if isinstance(rule, dict) else None
        if isinstance(validation, dict) and validation.get("status") == "warn":
            review_reasons.append(f"rule_validation_warn:{rule.get('type', 'unknown')}")
    return {
        "statement_type": statement_type,
        "currency_unit": _currency_unit(source_text),
        "period": _period(source_text),
        "header_bands": header_bands,
        "column_groups": column_groups,
        "account_rows": account_rows,
        "rules": rules,
        "quality": {
            "header_hierarchy_confidence": confidence["header"],
            "column_group_confidence": confidence["column_group"],
            "account_hierarchy_confidence": confidence["account"],
            "requires_review": bool(review_reasons),
            "review_reasons": review_reasons,
        },
    }


def _empty_structure(source_text: str, *, reason: str) -> dict[str, Any]:
    return {
        "statement_type": _statement_type(source_text, [], []),
        "currency_unit": _currency_unit(source_text),
        "period": _period(source_text),
        "header_bands": [],
        "column_groups": [],
        "account_rows": [],
        "rules": [],
        "quality": {
            "header_hierarchy_confidence": 0.0,
            "column_group_confidence": 0.0,
            "account_hierarchy_confidence": 0.0,
            "requires_review": True,
            "review_reasons": [reason],
        },
    }


def _statement_type(source_text: str, columns: list[dict[str, Any]], cells: list[dict[str, Any]]) -> str:
    haystack = " ".join(
        [
            source_text,
            *(str(col.get("header") or "") for col in columns),
            *(str(cell.get("text") or "") for cell in cells[:80]),
        ]
    )
    for keyword, statement_type in _STATEMENT_TYPES.items():
        if keyword in haystack:
            return statement_type
    if "实收资本" in haystack and "所有者权益" in haystack:
        return "owners_equity_changes"
    return "unknown"


def _currency_unit(source_text: str) -> str:
    if "金额单位" in source_text and "元" in source_text:
        return "CNY"
    return "CNY"


def _period(source_text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if "本年发生额" in source_text:
        out["current"] = "本年发生额"
    if "上年发生额" in source_text:
        out["previous"] = "上年发生额"
    return out


def _confidence(
    header_bands: list[dict[str, Any]],
    column_groups: list[dict[str, Any]],
    account_rows: list[dict[str, Any]],
) -> dict[str, float]:
    return {
        "header": 0.85 if header_bands else 0.0,
        "column_group": 0.8 if column_groups else 0.0,
        "account": 0.9 if account_rows else 0.0,
    }
