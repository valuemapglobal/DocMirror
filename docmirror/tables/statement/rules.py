"""Financial statement rule reconstruction and lightweight validation."""

from __future__ import annotations

from typing import Any


def build_statement_rules(account_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    roll_forward = _roll_forward_rule(account_rows)
    if roll_forward:
        rules.append(roll_forward)
    total_rules = _total_line_rules(account_rows)
    rules.extend(total_rules)
    return rules


def _roll_forward_rule(account_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    opening = _row_by_role(account_rows, "current_year_opening_balance")
    delta = _row_by_role(account_rows, "current_period_change")
    ending = _row_by_role(account_rows, "current_year_ending_balance")
    if not opening or not delta or not ending:
        return None
    return {
        "type": "roll_forward",
        "from": "本年年初余额",
        "delta": "本期增减变动金额",
        "to": "本年年末余额",
        "row_refs": {
            "opening_row_index": opening.get("row_index"),
            "delta_row_index": delta.get("row_index"),
            "ending_row_index": ending.get("row_index"),
        },
        "validation": _validate_roll_forward(opening, delta, ending),
    }


def _total_line_rules(account_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for row in account_rows:
        if not row.get("is_total"):
            continue
        parent = row.get("parent_row_index")
        if parent is None:
            continue
        component_rows = [
            item.get("row_index")
            for item in account_rows
            if item.get("parent_row_index") == parent and item.get("row_index") != row.get("row_index")
        ]
        if not component_rows:
            continue
        rules.append(
            {
                "type": "total_line",
                "target_row_index": row.get("row_index"),
                "component_row_indexes": component_rows,
                "validation": {"status": "not_evaluated", "reason": "component_sign_semantics_unknown"},
            }
        )
    return rules


def _validate_roll_forward(
    opening: dict[str, Any],
    delta: dict[str, Any],
    ending: dict[str, Any],
) -> dict[str, Any]:
    role_row_indexes = {
        opening.get("row_index"),
        delta.get("row_index"),
        ending.get("row_index"),
    }
    if len(role_row_indexes) < 3:
        return {"status": "not_evaluated", "reason": "ambiguous_role_rows"}
    opening_values = _values_by_col(opening)
    delta_values = _values_by_col(delta)
    ending_values = _values_by_col(ending)
    columns = sorted(set(opening_values) & set(delta_values) & set(ending_values))
    comparisons: list[dict[str, Any]] = []
    for col in columns:
        expected = opening_values[col] + delta_values[col]
        actual = ending_values[col]
        difference = actual - expected
        comparisons.append(
            {
                "col": col,
                "expected": expected,
                "actual": actual,
                "difference": difference,
                "status": "pass" if abs(difference) <= 0.05 else "warn",
            }
        )
    if not comparisons:
        return {"status": "not_evaluated", "reason": "missing_comparable_numeric_columns"}
    status = "pass" if all(item["status"] == "pass" for item in comparisons) else "warn"
    return {"status": status, "comparisons": comparisons}


def _values_by_col(row: dict[str, Any]) -> dict[int, float]:
    out: dict[int, float] = {}
    for value in row.get("values", []) or []:
        if not isinstance(value, dict):
            continue
        try:
            out[int(value.get("col", 0) or 0)] = float(value.get("number", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
    return out


def _row_by_role(account_rows: list[dict[str, Any]], role: str) -> dict[str, Any] | None:
    return next(
        (row for row in account_rows if row.get("role") == role or role in (row.get("matched_roles") or [])),
        None,
    )
