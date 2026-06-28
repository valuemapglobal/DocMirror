"""Account-row hierarchy reconstruction for financial statement tables."""

from __future__ import annotations

import re
from typing import Any

from docmirror.tables.statement.note_refs import extract_note_ref

ROW_ROLE_KEYWORDS = {
    "上年年末余额": "prior_year_ending_balance",
    "本年年初余额": "current_year_opening_balance",
    "本期增减变动金额": "current_period_change",
    "本年年末余额": "current_year_ending_balance",
    "年末余额": "ending_balance",
    "年初余额": "opening_balance",
    "资产总计": "asset_total",
    "负债合计": "liability_total",
    "所有者权益合计": "equity_total",
}


def build_account_rows(rows: list[dict[str, Any]], cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    parent_stack: dict[int, dict[str, Any]] = {}
    for row in rows:
        if row.get("role") == "header":
            continue
        row_index = int(row.get("index", 0) or 0)
        row_cells = sorted([cell for cell in cells if _cell_row(cell) == row_index], key=_cell_col)
        label_cell = _label_cell(row_cells)
        if not label_cell:
            continue
        label = str(label_cell.get("text") or "").strip()
        level = _row_level(label)
        matched_roles = matched_row_roles(label)
        role = matched_roles[0] if matched_roles else "line_item"
        parent = _parent_for_level(parent_stack, level)
        account_row = {
            "row_index": row_index,
            "label": label,
            "normalized_label": _normalize_label(label),
            "level": level,
            "role": role,
            "matched_roles": matched_roles,
            "parent_row_index": parent.get("row_index") if parent else None,
            "path": [*(parent.get("path", []) if parent else []), _normalize_label(label)],
            "is_total": _is_total_row(label, role),
            "note_ref": extract_note_ref(row_cells, label),
            "values": _numeric_values(row_cells),
            "evidence_ids": list(label_cell.get("evidence_ids") or []),
        }
        out.append(account_row)
        parent_stack[level] = account_row
        for child_level in [key for key in parent_stack if key > level]:
            parent_stack.pop(child_level, None)
    return out


def matched_row_roles(label: str) -> list[str]:
    roles = [value for keyword, value in ROW_ROLE_KEYWORDS.items() if keyword in label]
    if not roles:
        return []
    priority = {
        "prior_year_ending_balance": 10,
        "current_year_opening_balance": 20,
        "current_period_change": 30,
        "current_year_ending_balance": 40,
        "ending_balance": 50,
        "opening_balance": 60,
    }
    if label.strip().startswith(("三、", "三.")) and "current_period_change" in roles:
        return ["current_period_change", *[role for role in roles if role != "current_period_change"]]
    if label.strip().startswith(("四、", "四.")) and "current_year_ending_balance" in roles:
        return ["current_year_ending_balance", *[role for role in roles if role != "current_year_ending_balance"]]
    return sorted(dict.fromkeys(roles), key=lambda role: priority.get(role, 100))


def _label_cell(row_cells: list[dict[str, Any]]) -> dict[str, Any] | None:
    for cell in row_cells:
        text = str(cell.get("text") or "").strip()
        if text and _cell_col(cell) <= 1 and not _looks_like_note_or_number(text):
            return cell
    return next((cell for cell in row_cells if str(cell.get("text") or "").strip()), None)


def _numeric_values(row_cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for cell in row_cells:
        text = str(cell.get("text") or "").strip()
        number = _parse_number(text)
        if number is None:
            continue
        values.append(
            {
                "col": _cell_col(cell),
                "text": text,
                "number": number,
                "bbox": cell.get("bbox"),
                "evidence_ids": list(cell.get("evidence_ids") or []),
            }
        )
    return values


def _parse_number(text: str) -> float | None:
    cleaned = str(text or "").strip().replace(",", "").replace("，", "")
    if not cleaned or not re.search(r"\d", cleaned):
        return None
    negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        negative = True
        cleaned = cleaned[1:-1]
    if cleaned.startswith("（") and cleaned.endswith("）"):
        negative = True
        cleaned = cleaned[1:-1]
    cleaned = cleaned.replace(" ", "")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    value = float(match.group(0))
    return -abs(value) if negative else value


def _parent_for_level(parent_stack: dict[int, dict[str, Any]], level: int) -> dict[str, Any] | None:
    for candidate_level in range(level - 1, 0, -1):
        if candidate_level in parent_stack:
            return parent_stack[candidate_level]
    return None


def _row_level(label: str) -> int:
    stripped = label.strip()
    if stripped.startswith(("一、", "二、", "三、", "四、", "五、", "六、")):
        return 1
    if stripped.startswith(("（一）", "（二）", "（三）", "（四）", "（五）", "（六）")):
        return 2
    if stripped[:2] in {"1、", "2、", "3、", "4、", "5、", "6、"}:
        return 3
    return 1


def _normalize_label(label: str) -> str:
    stripped = str(label or "").strip()
    stripped = re.sub(r"^[一二三四五六七八九十]+[、.．]\s*", "", stripped)
    stripped = re.sub(r"^（[一二三四五六七八九十]+）\s*", "", stripped)
    stripped = re.sub(r"^[0-9]+[、.．]\s*", "", stripped)
    return stripped


def _is_total_row(label: str, role: str) -> bool:
    return role.endswith("_total") or any(keyword in label for keyword in ("合计", "总计", "小计"))


def _looks_like_note_or_number(text: str) -> bool:
    cleaned = text.replace(",", "").replace("，", "").strip()
    return bool(re.fullmatch(r"附注?[一二三四五六七八九十百0-9]+", cleaned) or re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned))


def _cell_row(cell: dict[str, Any]) -> int:
    return int(cell.get("row_index", cell.get("row", 0)) or 0)


def _cell_col(cell: dict[str, Any]) -> int:
    return int(cell.get("col_index", cell.get("column_index", cell.get("col", 0))) or 0)
