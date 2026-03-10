"""
Table structure fixEngine (Table Structure Fix Engine)
=============================================

通用、泛化的Table结构Post-processingFixModule。
在 OCR/Extractafter、最终OutputbeforeExecute，Fix常见的Table结构缺陷。

4 个独立FixFunction + 1 个统一Entry point:
    1. merge_split_rows     — Merge被Split的多行记录
    2. clean_cell_text      — Clean单元格内多余空格/Newline
    3. split_concat_cells   — Split粘连单元格 (如 Balance+Account number)
    4. align_row_columns    — Alignment行列数到Table header

Design principles:
    - 纯Function, 无Status, 无副作用
    - 每次Fix都做安全检查, 不确定时不修改
    - 对Empty table/单行Table直接Returns
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 1: Merge被Split的多行记录
# ═══════════════════════════════════════════════════════════════════════════════

# 纯时间Mode (HH:MM:SS 或 HH:MM)
_TIME_ONLY_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
# DateMode (YYYY-MM-DD 或 YYYY.MM.DD 或 YYYY/MM/DD)
_DATE_RE = re.compile(r"^\d{4}[-./]\d{1,2}[-./]\d{1,2}$")


def merge_split_rows(table: List[List[str]]) -> List[List[str]]:
    """Merge被Split的多行记录。

    规则 (按优先级):
      R1: 行首为纯时间 (HH:MM:SS) 且上一行首列为Date → Merge时间到Date
      R2: 行大partial列为空 (>60%) 且非汇总行 → Merge非Empty column到上一行

    泛化: 不Dependency特定列名或银行Format。
    """
    if not table or len(table) < 3:
        return table

    header = table[0]
    col_count = len(header)
    result = [header]
    i = 1

    while i < len(table):
        row = table[i]

        # ensure列数一致 (防御)
        if len(row) < col_count:
            row = row + [""] * (col_count - len(row))

        # ── R1: 纯时间行 → Merge到上一行Date ──
        first_cell = row[0].strip() if row else ""
        if (
            result  # 有上一行
            and len(result) > 1  # notTable header
            and _TIME_ONLY_RE.match(first_cell)
        ):
            prev_row = list(result[-1])
            prev_first = prev_row[0].strip()

            if _DATE_RE.match(prev_first):
                # Merge: "2025-12-24" + "01:21:34" → "2025-12-24 01:21:34"
                prev_row[0] = f"{prev_first} {first_cell}"
                # MergeOther非Empty column
                for j in range(1, min(len(row), len(prev_row))):
                    if row[j].strip() and not prev_row[j].strip():
                        prev_row[j] = row[j]
                    elif row[j].strip() and prev_row[j].strip():
                        prev_row[j] = prev_row[j] + " " + row[j]
                result[-1] = prev_row
                i += 1
                continue

        # ── R2: 大partial列为空 → Merge到上一行 ──
        non_empty = sum(1 for c in row if c.strip())
        empty_ratio = 1 - (non_empty / col_count) if col_count > 0 else 0

        if (
            empty_ratio > 0.6
            and len(result) > 1  # notTable header
            and non_empty > 0  # not全Empty row
            and not _is_summary_row(row)  # not汇总行
        ):
            prev_row = list(result[-1])
            for j in range(min(len(row), len(prev_row))):
                if row[j].strip() and not prev_row[j].strip():
                    prev_row[j] = row[j]
                elif row[j].strip() and prev_row[j].strip():
                    # 追加 (对方Account name等多行文本)
                    prev_row[j] = prev_row[j] + row[j]
            result[-1] = prev_row
            i += 1
            continue

        result.append(row)
        i += 1

    return result


def _is_summary_row(row: List[str]) -> bool:
    """Detect汇总行 (不应被Merge)。"""
    text = "".join(str(c) for c in row)
    summary_keywords = ["总收入", "总支出", "合计", "总计", "小计", "本页", "累计"]
    return any(kw in text for kw in summary_keywords)


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 2: Clean单元格内文本
# ═══════════════════════════════════════════════════════════════════════════════

# 中文字符之间的空格 (应remove)
_CJK_SPACE_RE = re.compile(
    r"([\u4e00-\u9fff\u3400-\u4dbf])\s+([\u4e00-\u9fff\u3400-\u4dbf])"
)


def clean_cell_text(text: str) -> str:
    """Clean单元格内多余空格/Newline。

    规则:
      - 中文字符之间的空格 → remove (PDF 多行文本重组产物)
      - retain: 英文之间、数字之间、中英之间的空格
      - 首尾Whitespace去除
    """
    if not text or not text.strip():
        return text.strip()

    # replaceNewline为空格
    text = text.replace("\n", " ").replace("\r", "")

    # 多次迭代remove中文间空格 (Processing连续 "A B C" → "ABC")
    prev = ""
    while prev != text:
        prev = text
        text = _CJK_SPACE_RE.sub(r"\1\2", text)

    return text.strip()


def clean_table_cells(table: List[List[str]]) -> List[List[str]]:
    """对Tableall单元格ExecuteText cleanup。"""
    return [
        [clean_cell_text(cell) if isinstance(cell, str) else cell for cell in row]
        for row in table
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 3: Split粘连单元格
# ═══════════════════════════════════════════════════════════════════════════════

# 数字→字母边界 (如 "110.9731080243CNYFC")
_NUM_ALPHA_BOUNDARY_RE = re.compile(
    r"(\d{1,3}\.\d{2})"           # Amountpartial (如 110.97)
    r"(\d{5,}[A-Z]*\d*)"         # Account numberpartial (如 31080243CNYFC0445)
)


def split_concatenated_cells(
    table: List[List[str]],
) -> List[List[str]]:
    """Split粘连单元格 — 当行列数少于Table header时尝试Split。

    规则:
      - 只在行列数 < Table header列数时Trigger
      - Detect 数字.数字+数字字母 的粘连Mode
      - Split后列数应等于Table header列数
    """
    if not table or len(table) < 2:
        return table

    header = table[0]
    header_col_count = len(header)
    result = [header]

    for row in table[1:]:
        if len(row) >= header_col_count:
            result.append(row)
            continue

        # 尝试Split粘连单元格
        deficit = header_col_count - len(row)
        if deficit <= 0:
            result.append(row)
            continue

        new_row = []
        splits_done = 0
        for cell in row:
            if splits_done >= deficit and len(new_row) + (len(row) - len(new_row)) <= header_col_count:
                new_row.append(cell)
                continue

            # DetectAmount+Account number粘连
            m = _NUM_ALPHA_BOUNDARY_RE.match(str(cell))
            if m and splits_done < deficit:
                new_row.append(m.group(1))  # Amount
                new_row.append(m.group(2))  # Account number
                splits_done += 1
            else:
                new_row.append(cell)

        # 如果Split后列数Match, using新行
        if len(new_row) == header_col_count:
            result.append(new_row)
        else:
            result.append(row)  # SplitFailed, retain原行

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 4: Alignment行列数
# ═══════════════════════════════════════════════════════════════════════════════

def align_row_columns(table: List[List[str]]) -> List[List[str]]:
    """Alignmentall行的列数到Table header列数。

    规则:
      - 列数少于Table header → 末尾补空字符串
      - 列数多于Table header → 尾部多余列Merge到最后一列
    """
    if not table:
        return table

    header = table[0]
    target = len(header)
    result = [header]

    for row in table[1:]:
        if len(row) == target:
            result.append(row)
        elif len(row) < target:
            result.append(row + [""] * (target - len(row)))
        else:
            # 多余列Merge到最后一列
            merged = row[:target - 1] + [" ".join(str(c) for c in row[target - 1:] if c)]
            result.append(merged)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 5: UnderlineFooterClean
# ═══════════════════════════════════════════════════════════════════════════════

# Match ≥3 个连续Underline (Footer分隔线)
_UNDERLINE_RE = re.compile(r"_{3,}")


def strip_underline_footer(table: List[List[str]]) -> List[List[str]]:
    """Clean单元格中Underline拼接的Footer统计Information。

    Mode: "4085.26___支出交易总额:...___收入交易总额:...___合计笔数:..."
    规则: 截断到第一个 ___（retain前面的实际Data值）。

    泛化: 不Dependency特定列名, anycontains ___ 的单元格都Processing。
    """
    for row in table:
        for ci in range(len(row)):
            cell = row[ci] or ""
            m = _UNDERLINE_RE.search(cell)
            if m:
                row[ci] = cell[: m.start()].rstrip()
    return table


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 6: Crop尾部Empty column
# ═══════════════════════════════════════════════════════════════════════════════


def trim_trailing_empty_columns(table: List[List[str]]) -> List[List[str]]:
    """Crop全为空的尾部列。

    泛化: 只裁尾部, 不影响中间的Empty column。
    """
    if not table or not table[0]:
        return table

    col_count = max(len(row) for row in table)
    trim_to = col_count
    for ci in range(col_count - 1, -1, -1):
        all_empty = all(
            not (row[ci] if ci < len(row) else "").strip()
            for row in table
        )
        if all_empty:
            trim_to = ci
        else:
            break

    if trim_to < col_count:
        table = [row[:trim_to] for row in table]
    return table


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 7: 纯数字空格Merge
# ═══════════════════════════════════════════════════════════════════════════════

# Match "数字 数字" Mode (中间only空格, 无字母/汉字)
_DIGIT_SPACE_RE = re.compile(r"^[\d\s]+$")


def merge_digit_spaces(table: List[List[str]]) -> List[List[str]]:
    """Merge纯数字单元格中间的空格。

    Mode: "6216911304 963684" → "6216911304963684"
    规则: 只对纯数字+空格的 cell 生效, 不影响含字母/汉字的 cell。

    泛化: 自动Detect, 不Dependency列名, 适用一切Bank statement。
    """
    for row in table[1:]:  # SkipTable header
        for ci in range(len(row)):
            cell = (row[ci] or "").strip()
            if cell and _DIGIT_SPACE_RE.match(cell) and " " in cell:
                row[ci] = cell.replace(" ", "")
    return table


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 8: Clean粘连在Data值后面的双语列Title
# ═══════════════════════════════════════════════════════════════════════════════

# 常见的双语列Title尾缀 (英文partial) — 按长度降序Match
_BILINGUAL_SUFFIXES = [
    "Counterparty Institution", "Counterparty Name",
    "Transaction Amount", "Transaction Date",
    "Account Balance", "Abstract Code",
    "Serial Number", "Description",
    "Debit", "Credit",
]
# 构建正则: Match "中文...英文尾缀" Mode
_BILINGUAL_SUFFIX_RE = re.compile(
    r"([\u4e00-\u9fff][\u4e00-\u9fff\s]*)\s*("
    + "|".join(re.escape(s) for s in _BILINGUAL_SUFFIXES)
    + r")\s*$"
)


def strip_header_labels_from_cells(table: List[List[str]]) -> List[List[str]]:
    """CleanData单元格中粘连的双语列Title后缀。

    Mode: "0.90DebitDebit" → "0.90"
          "浦发银行重庆分行营业部对手机构 Counterparty Institution" → "浦发银行重庆分行营业部"

    规则: Detect cell 末尾的 "中文+英文" 列TitleComposition, 截断到中文partialbefore。
    泛化: 不Dependency特定列, based on通用双语列TitleKeywords。
    """
    for row in table[1:]:  # SkipTable header
        for ci in range(len(row)):
            cell = (row[ci] or "").strip()
            if not cell or len(cell) < 5:
                continue
            m = _BILINGUAL_SUFFIX_RE.search(cell)
            if m:
                # 截断到中文列Titlebeginbefore
                row[ci] = cell[: m.start()].rstrip()
    return table


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 9: remove全Empty table
# ═══════════════════════════════════════════════════════════════════════════════


def remove_empty_tables(tables: List[List[List[str]]]) -> List[List[List[str]]]:
    """removeall cell 均为空的Table。

    泛化: 只删全Empty table, 不影响有anyData的Table。
    """
    result = []
    for table in tables:
        has_content = any(
            (cell or "").strip()
            for row in table
            for cell in row
        )
        if has_content:
            result.append(table)
        else:
            logger.debug("[DocMirror] removed empty table")
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 11: Split粘连在Account name开头的Account number数字
# ═══════════════════════════════════════════════════════════════════════════════

# ≥10位连续数字 + 中文 (Account number粘连Account name)
_ACCT_PREFIX_RE = re.compile(r"^(\d{10,})([\u4e00-\u9fff].*)$")


def split_account_from_name(table: List[List[str]]) -> List[List[str]]:
    """Split粘连在Account name列开头的长数字Account number。

    Mode: "7065018800015镇江一生一世好游戏有限公司" →
          对方Account="7065018800015"  对方Account name="镇江一生一世好游戏有限公司"

    规则:
      - 如果 cell 以 ≥10 位连续数字开头, 后接中文 → Split
      - 数字partialMerge到前一列 (如果前一列Table header含 "Account"/"Account number")
      - 泛化: 不Dependency列名 hard-coding, based onTable header内容Match
    """
    if not table or len(table) < 2 or len(table[0]) < 2:
        return table

    header = table[0]

    # 找 "对方Account"/"对方Account number" 列和其右邻列
    acct_col = None
    for ci, h in enumerate(header):
        h_text = (h or "").strip()
        if ("Account" in h_text or "Account number" in h_text) and "对方" in h_text:
            if ci + 1 < len(header):
                acct_col = ci
                break

    if acct_col is None:
        return table

    name_col = acct_col + 1

    for row in table[1:]:
        if name_col >= len(row):
            continue
        cell = (row[name_col] or "").strip()
        m = _ACCT_PREFIX_RE.match(cell)
        if m:
            digits, name = m.group(1), m.group(2)
            # Merge数字到Account列 (prepend, 用空格分隔已有值)
            existing = (row[acct_col] or "").strip()
            row[acct_col] = (digits + " " + existing).strip() if existing else digits
            row[name_col] = name.strip()

    return table


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 12: 剥离货币前缀
# ═══════════════════════════════════════════════════════════════════════════════

# Match "RMB 352.10" 或 "CNY352.10" 或 "USD 1,000.00"
_CURRENCY_PREFIX_RE = re.compile(
    r"^(RMB|CNY|USD|EUR|JPY|HKD|GBP)\s*"
    r"([\-\d,]+\.?\d*)\s*$"
)


def strip_currency_prefix(table: List[List[str]]) -> List[List[str]]:
    """剥离单元格中的货币代码前缀。

    Mode: "RMB 352.10" → "352.10", "RMB7.77" → "7.77"
    规则: 只Processing "货币代码+数字" 的纯Amount cell, 不影响含文字的 cell。
    泛化: supports RMB/CNY/USD/EUR/JPY/HKD/GBP。
    """
    for row in table[1:]:  # SkipTable header
        for ci in range(len(row)):
            cell = (row[ci] or "").strip()
            if not cell:
                continue
            m = _CURRENCY_PREFIX_RE.match(cell)
            if m:
                row[ci] = m.group(2)
    return table


# ═══════════════════════════════════════════════════════════════════════════════
# 统一Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def fix_table_structure(table: List[List[str]]) -> List[List[str]]:
    """Table structure fix统一Entry point。

    按顺序Execute:
      1. Line merging (Date+时间, 多行单元格)
      2. 粘连单元格Split (Balance+Account number)
      3. 列数Alignment
      4. 单元格Text cleanup
      5. UnderlineFooterClean
      6. 尾部Empty columnCrop
      7. 纯数字空格Merge
      8. 双语列TitleClean
      9. Account numberAccount nameSplit
      10. 货币前缀剥离

    Args:
        table: 原始Table (二维字符串List, 第 0 行为Table header)。

    Returns:
        Fix后的Table。
    """
    if not table or len(table) < 2:
        return table

    original_rows = len(table)

    table = merge_split_rows(table)              # Fix 1
    table = split_concatenated_cells(table)       # Fix 3
    table = align_row_columns(table)              # Fix 4
    table = clean_table_cells(table)              # Fix 2
    table = strip_underline_footer(table)         # Fix 5
    table = trim_trailing_empty_columns(table)    # Fix 6
    table = merge_digit_spaces(table)             # Fix 7
    table = strip_header_labels_from_cells(table) # Fix 8
    table = split_account_from_name(table)        # Fix 11
    table = strip_currency_prefix(table)          # Fix 12
    table = remove_empty_interior_columns(table)  # Fix 13

    fixed_rows = len(table)
    if fixed_rows != original_rows:
        logger.info(
            f"[DocMirror] table_structure_fix: "
            f"{original_rows} → {fixed_rows} rows "
            f"(merged {original_rows - fixed_rows})"
        )

    return table


def remove_empty_interior_columns(table: List[List[str]]) -> List[List[str]]:
    """Delete全空的Internal列 (含Table header也为空或为相邻列重复)。

    交通银行等双行Table header场景: DebitTransaction amount/CreditTransaction amount 被 post_process Merge后,
    产生Empty column + 重复列名。本Function只Delete **allData行都为空** 的列。

    Args:
        table: Fix后的Table, 第 0 行为Table header。

    Returns:
        DeleteEmpty column后的Table。
    """
    if not table or len(table) < 2:
        return table

    n_cols = len(table[0])
    if n_cols <= 1:
        return table

    # 找出allData行全为空的列
    empty_cols: set = set()
    for ci in range(n_cols):
        if all(
            not (row[ci] if ci < len(row) else "").strip()
            for row in table[1:]  # skip header
        ):
            empty_cols.add(ci)

    if not empty_cols:
        return table

    # 构建Table header出现次数, 用于Detect重复
    header_vals = [(table[0][ci] if ci < len(table[0]) else "").strip() for ci in range(n_cols)]
    header_counts: dict = {}
    for h in header_vals:
        header_counts[h] = header_counts.get(h, 0) + 1

    # Delete条件: Data全空 AND (Table header为空 OR Table header是重复值)
    cols_to_remove: set = set()
    for ci in empty_cols:
        hv = header_vals[ci]
        if not hv or header_counts.get(hv, 0) > 1:
            cols_to_remove.add(ci)

    if not cols_to_remove:
        return table

    keep = [ci for ci in range(n_cols) if ci not in cols_to_remove]
    result = []
    for row in table:
        result.append([row[ci] if ci < len(row) else "" for ci in keep])

    logger.debug(
        f"[fix] removed {len(cols_to_remove)} empty interior columns: "
        f"{sorted(cols_to_remove)}"
    )
    return result




