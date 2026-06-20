"""
Wrap recovery — fixes line-wrapped and truncated cell content.

Purpose: Recovers wrapped newlines in cells, completes truncated time/direction
columns, and normalizes char encoding in ledger cells.

Main components: ``ColumnWrapRecovery``, ``clean_cell_newlines``,
``complete_truncated_times``.

Upstream: Ledger/borderless tables after initial normalize.

Downstream: ``table.ledger_postprocess``, exported cell text.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_RE_DATE = re.compile(r"^\d{4}[-./年]\d{1,2}[-./月]\d{1,2}日?$")
_RE_TIME = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")


def clean_cell_newlines(rows: list[list[str]]) -> list[list[str]]:
    """Clean embedded newlines: trade_id←concat, time←join with space, others←concat."""
    for row in rows:
        for ci in range(len(row)):
            cell = row[ci]
            if "\n" not in cell:
                continue
            parts = cell.split("\n")
            if (
                ci == 1
                and _RE_DATE.match(parts[0].strip())
                and (_RE_TIME.match(parts[-1].strip()) if len(parts) > 1 else False)
            ):
                row[ci] = parts[0].strip() + " " + parts[-1].strip()  # date + time
            else:
                row[ci] = "".join(p.strip() for p in parts)  # just concatenate
    return rows


def complete_direction_column(
    rows: list[list[str]], amount_col: int = 5, direction_col: int = 3, type_col: int = 2
) -> list[list[str]]:
    """Infer empty direction from type name."""
    for row in rows:
        while len(row) <= max(amount_col, direction_col, type_col):
            row.append("")
        if row[direction_col].strip():
            continue
        t = row[type_col].strip()
        if "收入" in t or "转入" in t:
            row[direction_col] = "收入"
        elif "支出" in t or "消费" in t or "充值" in t:
            row[direction_col] = "支出"
        elif "提现" in t:
            row[direction_col] = "其他"
    return rows


def normalize_char_encoding(rows: list[list[str]]) -> list[list[str]]:
    """Fullwidth brackets/commas → ASCII."""
    tr = str.maketrans({"\uff08": "(", "\uff09": ")", "\uff0c": ",", "\uff5e": "~", "\u301c": "~", "\u3000": " "})
    for row in rows:
        for ci in range(len(row)):
            row[ci] = row[ci].translate(tr)
    return rows


def normalize_punctuation(rows, type_col=None):
    """Clean Chinese punctuation spacing and normalize brackets.

    1. Remove space before Chinese punct: " 、" -> "、", " ）" -> "）"
    2. For type column: ASCII brackets with Chinese content -> fullwidth
    """
    _CLEAN_PRE_SPACE = re.compile(r" ([、。，）；】\u3001\uff0c\uff09])")
    for row in rows:
        for ci in range(len(row)):
            row[ci] = _CLEAN_PRE_SPACE.sub(r"\1", row[ci])
            # 2. For type column: ASCII (中文) -> （中文）
            if type_col is not None and ci == type_col:
                row[ci] = re.sub(r"\( ?([^)]*[\u4e00-\u9fff][^)]*?) ?\)", r"（\1）", row[ci])
    return rows


def _header_col_idx(table: list[list[str]], keywords: list[str], default: int) -> int:
    if not table:
        return default
    for h in table[0]:
        for kw in keywords:
            if kw in h.strip():
                return list(table[0]).index(h)
    return default


def complete_truncated_times(
    rows: list[list[str]],
    time_col: int = 1,
    trade_id_col: int = 0,
) -> list[list[str]]:
    """补齐被截断的时间戳（缺时分秒）。

    微信流水的 trade_id 中包含时间信息：
    '1000050001202208091314970454656'
     ├─ 前缀 ┤├─ 日期 ┤├── 时间戳 ┤
    """
    if not rows:
        return rows

    max_cols = max(len(r) for r in rows)
    rows = [r + [""] * (max_cols - len(r)) for r in rows]

    for row in rows:
        time_val = row[time_col].strip()
        # 只有日期(YYYY-MM-DD)，没有时分秒 → 需要补齐
        if re.match(r"^\d{4}-\d{2}-\d{2}$", time_val):
            trade_id = row[trade_id_col].strip()
            # 从 trade_id 中提取时间：格式 YYYYMMDDHHMMSS
            # 位置: 前缀(10位) + 日期(8位) + 时分秒(6位)
            if len(trade_id) >= 24:
                time_suffix = trade_id[18:24]  # HHMMSS
                if time_suffix.isdigit() and len(time_suffix) == 6:
                    hh, mm, ss = int(time_suffix[:2]), int(time_suffix[2:4]), int(time_suffix[4:6])
                    if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59:
                        row[time_col] = f"{time_val} {time_suffix[:2]}:{time_suffix[2:4]}:{time_suffix[4:6]}"

    return rows


class ColumnWrapRecovery:
    """Unified post-extraction cell content cleanup."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def process(
        self, tables: list[list[list[str]]], layer: str, conf: float
    ) -> tuple[list[list[list[str]]], str, float]:
        if not tables:
            return tables, layer, conf
        out = []
        for t in tables:
            if not t or len(t) < 2:
                out.append(t)
                continue
            t = clean_cell_newlines(t)
            t = complete_direction_column(
                t, _header_col_idx(t, ["金额"], 5), _header_col_idx(t, ["收/支"], 3), _header_col_idx(t, ["类型"], 2)
            )
            t = normalize_char_encoding(t)
            out.append(t)
        return out, layer, conf


__all__ = [
    "ColumnWrapRecovery",
    "clean_cell_newlines",
    "complete_direction_column",
    "normalize_char_encoding",
    "normalize_punctuation",
    "complete_truncated_times",
]
