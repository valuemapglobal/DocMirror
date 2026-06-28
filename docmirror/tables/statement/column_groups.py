"""Column-group reconstruction for financial statement tables."""

from __future__ import annotations

from typing import Any

_OWNER_EQUITY_CHILD_LABELS = (
    "实收资本",
    "股本",
    "资本公积",
    "盈余公积",
    "未分配利润",
    "其他综合收益",
    "专项储备",
)


def build_column_groups(
    columns: list[dict[str, Any]],
    header_bands: list[dict[str, Any]],
    *,
    source_text: str,
    statement_type: str,
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    groups.extend(_spanning_header_groups(columns, header_bands))
    groups.extend(_owner_equity_groups(columns, source_text=source_text, statement_type=statement_type))
    groups.extend(_single_column_equity_groups(columns))
    return _dedupe_groups(groups)


def _spanning_header_groups(
    columns: list[dict[str, Any]],
    header_bands: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for band in header_bands:
        for cell in band.get("cells", []) or []:
            if not isinstance(cell, dict):
                continue
            text = str(cell.get("text") or "").strip()
            col_range = cell.get("col_range") if isinstance(cell.get("col_range"), list) else None
            if not text or not col_range or len(col_range) != 2:
                continue
            start, end = int(col_range[0] or 0), int(col_range[1] or 0)
            if end <= start:
                continue
            groups.append(
                {
                    "id": f"cg:header:{start}:{end}",
                    "label": text,
                    "col_range": [start, end],
                    "child_column_ids": _column_ids(columns, start, end),
                    "source": "merged_header_band",
                    "confidence": 0.86,
                }
            )
    return groups


def _owner_equity_groups(
    columns: list[dict[str, Any]],
    *,
    source_text: str,
    statement_type: str,
) -> list[dict[str, Any]]:
    haystack = " ".join([source_text, *[str(col.get("header") or "") for col in columns]])
    if statement_type != "owners_equity_changes" and "归属于母公司所有者权益" not in haystack:
        return []

    child_indexes = [
        int(col.get("index", idx) or idx)
        for idx, col in enumerate(columns)
        if any(label in str(col.get("header") or "") for label in _OWNER_EQUITY_CHILD_LABELS)
    ]
    if not child_indexes and len(columns) >= 4:
        child_indexes = list(range(1, max(len(columns) - 1, 2)))
    if not child_indexes:
        return []
    return [
        {
            "id": "cg:parent_equity",
            "label": "归属于母公司所有者权益",
            "col_range": [min(child_indexes), max(child_indexes)],
            "child_column_ids": _column_ids(columns, min(child_indexes), max(child_indexes)),
            "source": "owner_equity_statement_kernel",
            "confidence": 0.88 if "归属于母公司所有者权益" in haystack else 0.72,
        }
    ]


def _single_column_equity_groups(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for idx, col in enumerate(columns):
        header = str(col.get("header") or "")
        if "少数股东权益" not in header and "所有者权益合计" not in header:
            continue
        col_index = int(col.get("index", idx) or idx)
        groups.append(
            {
                "id": f"cg:{col_index}",
                "label": header,
                "col_range": [col_index, col_index],
                "child_column_ids": [str(col.get("id") or f"col:{col_index}")],
                "source": "single_equity_column",
                "confidence": 0.9,
            }
        )
    return groups


def _column_ids(columns: list[dict[str, Any]], start: int, end: int) -> list[str]:
    return [
        str(columns[idx].get("id") or f"col:{idx}")
        for idx in range(max(start, 0), min(end + 1, len(columns)))
    ]


def _dedupe_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, tuple[int, int]]] = set()
    out: list[dict[str, Any]] = []
    for group in groups:
        col_range = group.get("col_range") if isinstance(group.get("col_range"), list) else [0, 0]
        key = (str(group.get("label") or ""), (int(col_range[0] or 0), int(col_range[1] or 0)))
        if key in seen:
            continue
        seen.add(key)
        out.append(group)
    return out
