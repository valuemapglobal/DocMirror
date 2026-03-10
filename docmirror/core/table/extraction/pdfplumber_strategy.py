"""Auto-split from table_extraction.py"""

from __future__ import annotations

import concurrent.futures
import contextvars
import logging
import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...utils.text_utils import _is_cjk_char, _smart_join, normalize_table
from ...utils.vocabulary import (
    KNOWN_HEADER_WORDS,
    PIPE_CHARS,
    HLINE_CHARS,
    _ALL_BORDER_CHARS,
    _is_header_row,
    _normalize_for_vocab,
    _score_header_by_vocabulary,
    _RE_IS_DATE,
    _RE_IS_AMOUNT,
)

logger = logging.getLogger(__name__)


# Forward import for TABLE_SETTINGS
from .classifier import TABLE_SETTINGS

def _recover_header_from_zone(
    tables: List[List[List[str]]],
    work_page,
    table_zone_bbox: Optional[Tuple[float, float, float, float]],
    original_page,
) -> List[List[List[str]]]:
    """当 pdfplumber 的 lines/text 策略丢弃了Table header行时, 从 zone 字符中resume。

    原理: pdfplumber 的 horizontal_strategy="lines" 会从第一条水平线beginExtract,
    如果Table header行在第一条线above但仍在 zone 内, 就会被丢弃。
    本FunctionDetect这种情况并将丢失的Table header行插回Table首行。

    using x CoordinatesAlignment: 将Table header词按 x 位置Map到Data列, 解决Inconsistent column count的问题
    (e.g.Data列 "RMB 2936.78" 被 pdfplumber 拆成两列, 对应一个Table header "AccountBalance")。
    """
    if not tables or not table_zone_bbox:
        return tables

    main_table = tables[0]
    if not main_table or len(main_table) < 1:
        return tables

    # 如果Table header已存在于前 10 行中任意位置, 无需 recovery
    # (post_process_table 的 _score 扫描会正确找到它)
    if any(_score_header_by_vocabulary(row) >= 3 for row in main_table[:10]):
        return tables

    # 从 zone Region extraction words, 找Table header候选行
    try:
        x0, y0, x1, y1 = table_zone_bbox
        zone_page = original_page.crop((x0, y0, x1, y1))
        words = zone_page.extract_words(keep_blank_chars=True, x_tolerance=2)
        if not words:
            return tables
    except Exception:
        return tables

    # 按 y 分组
    from collections import defaultdict
    y_rows: Dict[int, list] = defaultdict(list)
    for w in words:
        yk = round(w["top"] / 3) * 3
        y_rows[yk].append(w)

    sorted_yks = sorted(y_rows.keys())
    if len(sorted_yks) < 2:
        return tables

    # 在前几行中找词 tableMatch最好的行
    best_yk = -1
    best_score = 0
    for yk in sorted_yks[:5]:
        texts = [w["text"].strip() for w in y_rows[yk] if w["text"].strip()]
        score = sum(1 for t in texts if t in KNOWN_HEADER_WORDS)
        if score > best_score:
            best_score = score
            best_yk = yk

    if best_score < 3 or best_yk < 0:
        return tables

    # 检查: Table headerWhether已在首行中 (无需resume)
    header_words = sorted(y_rows[best_yk], key=lambda w: w["x0"])
    header_texts = [w["text"].strip() for w in header_words if w["text"].strip()]
    first_row_text = set(c.strip() for c in main_table[0] if (c or "").strip())
    header_text_set = set(header_texts)
    if len(first_row_text & header_text_set) >= 2:
        return tables

    # ── x CoordinatesAlignment: 将Table header词Map到Data列 ──
    n_cols = len(main_table[0])

    # 获取 pdfplumber Table的列边界 (vertical edges)
    col_midpoints = None
    try:
        tf = work_page.debug_tablefinder(table_settings=TABLE_SETTINGS)
        v_edges = sorted(set(
            round(e['x0'], 1) for e in tf.edges
            if abs(e['x0'] - e['x1']) < 1  # 垂直线
        ))
        if len(v_edges) >= 2:
            col_midpoints = [
                (v_edges[i] + v_edges[i + 1]) / 2
                for i in range(len(v_edges) - 1)
            ]
    except Exception:
        pass

    if col_midpoints and len(col_midpoints) == n_cols:
        # 对eachTable header词, 找 x 中心最近的Data列
        header_row = [""] * n_cols
        for hw in header_words:
            text = hw["text"].strip()
            if not text:
                continue
            hx_mid = (hw["x0"] + hw["x1"]) / 2
            best_col = min(range(len(col_midpoints)),
                           key=lambda ci: abs(col_midpoints[ci] - hx_mid))
            if header_row[best_col]:
                header_row[best_col] += text
            else:
                header_row[best_col] = text

        logger.info(
            f"[v2] header recovery (x-aligned): vocab_score={best_score}, "
            f"header={header_row[:4]}..."
        )
        # 去除 main_table 中重复的Table header行 (vocab_score >= 3), retain preamble KV 行
        clean_body = [
            row for row in main_table
            if _score_header_by_vocabulary(row) < 3
        ]
        new_table = [header_row] + clean_body
        return [new_table] + tables[1:]

    # Fallback: 简单Alignment (无法获取Data行 words 时)
    header_row = list(header_texts)
    if len(header_row) > n_cols:
        header_row = header_row[:n_cols]
    elif len(header_row) < n_cols:
        header_row = header_row + [""] * (n_cols - len(header_row))

    logger.info(
        f"[v2] header recovery (fallback): vocab_score={best_score}, "
        f"header={header_row[:4]}..."
    )
    # 去除 main_table 中重复的Table header行, retain preamble KV 行
    clean_body = [
        row for row in main_table
        if _score_header_by_vocabulary(row) < 3
    ]
    new_table = [header_row] + clean_body
    return [new_table] + tables[1:]

