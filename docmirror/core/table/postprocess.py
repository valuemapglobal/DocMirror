"""
Table post-processing (Table Post-processing)
====================================

从 layout_analysis.py Split的Table post-processing系统。
contains post_process_table、_strip_preamble、_fix_header_by_vocabulary、
_clean_cell、_merge_split_rows、_extract_summary_entities 等。
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from ..utils.text_utils import (
    _is_cjk_char, _smart_join, normalize_text, normalize_table, parse_amount,
    _RE_DATE_COMPACT, _RE_DATE_HYPHEN, _RE_TIME, _RE_ONLY_CJK,
)
from ..utils.vocabulary import (
    KNOWN_HEADER_WORDS,
    VOCAB_BY_CATEGORY,
    _is_data_row,
    _is_header_row,
    _is_junk_row,
    _normalize_for_vocab,
    _score_header_by_vocabulary,
    _RE_IS_AMOUNT,
    _RE_IS_DATE,
    _RE_VALID_DATE,
)

logger = logging.getLogger(__name__)

def _extract_preamble_kv(rows: List[List[str]]) -> Dict[str, str]:
    """从 pre-header 行中Extract KV 元Data对。

    规则: 相邻非空单元格满足 (中文标签, 数值/Date) Mode时Extract为 KV 对。
    示例行: ['汇出总Amount（Debit）', None, '3,507,280.66', None, '汇入总Amount（Credit）', ...]
            → None 被Skip后 → ['汇出总Amount（Debit）', '3,507,280.66', '汇入总Amount（Credit）', ...]
    """
    kv: Dict[str, str] = {}
    for row in rows:
        # 先Filter掉 None/空格, 得到紧凑的非空 cell List
        cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
        i = 0
        while i < len(cells) - 1:
            key = cells[i]
            val = cells[i + 1]
            # key: 非空, contains汉字, 不像纯数值 / Date
            # val: 非空, 是Amount/Date/纯数字
            if (
                key and val
                and re.search(r"[\u4e00-\u9fff]", key)
                and not _RE_IS_DATE.match(key)
                and not _RE_IS_AMOUNT.match(key.replace(",", ""))
            ):
                clean_val = val.replace(",", "").replace("¥", "").replace(" ", "")
                is_num_or_date = bool(
                    _RE_IS_DATE.search(val) or
                    (_RE_IS_AMOUNT.match(clean_val) if clean_val else False)
                )
                if is_num_or_date:
                    kv[key] = val
                    i += 2  # Skip value
                    continue
            i += 1
    return kv


def _strip_preamble(
    rows: List[List[str]],
    confirmed_header: List[str],
    categories: Optional[List[str]] = None,
) -> List[List[str]]:
    """去除续 table页开头的重复汇总行和重复Table header行。

    Args:
        rows: 待Filter的行List
        confirmed_header: 已确认的Table header行
        categories: vocab Match所用的Document类别; Default为 ["BANK_STATEMENT"]
    """
    if not confirmed_header or not rows:
        return rows

    # 确认Table header非空 cell 的集合
    header_cells = {
        _normalize_for_vocab(c).strip()
        for c in confirmed_header
        if c and c.strip()
    }

    if not categories:
        categories = ["BANK_STATEMENT"]

    max_scan = min(10, len(rows))

    # 两阶段扫描:
    # 阶段1: 扫描前 max_scan 行, 找到最后一个 vocab_score >= 3 的行 (重复Table header行)
    last_header_idx = -1
    for i in range(max_scan):
        vs = _score_header_by_vocabulary(rows[i], categories=categories)
        if vs >= 3:
            last_header_idx = i

    if last_header_idx >= 0:
        # F-7: 剥离Protected — 最多剥离 5 行
        if last_header_idx > 5:
            logger.warning(
                f"[v2] strip_preamble: vocab header at row {last_header_idx} "
                f"(> 5 rows) — capping to avoid data loss"
            )
            last_header_idx = 5
        logger.debug(
            f"[v2] strip_preamble: skip rows 0-{last_header_idx} "
            f"(vocab repeated header at row {last_header_idx})"
        )
        return rows[last_header_idx + 1:]

    # 阶段2: 无重复Table header, 尝试 header-similarity Match
    for i in range(max_scan):
        row = rows[i]
        norm_cells = {
            _normalize_for_vocab(c).strip()
            for c in row if c and c.strip()
        }
        if header_cells and norm_cells:
            overlap = len(norm_cells & header_cells) / len(header_cells)
            if overlap >= 0.5:
                logger.debug(
                    f"[v2] strip_preamble: skip rows 0-{i} "
                    f"(header overlap={overlap:.2f})"
                )
                return rows[i + 1:]
        # 一旦遇到真实Data行, stop相似度Detect
        if _is_data_row(row):
            break

    return rows


def post_process_table(
    table_data: List[List[str]],
    confirmed_header: Optional[List[str]] = None,
) -> Tuple[Optional[List[List[str]]], Dict[str, str]]:
    """通用Table post-processing — 无KeywordsDependency。

    Args:
        table_data: 原始二维Table
        confirmed_header: 已确认的Table header (用于续 table preamble Filter)

    Returns:
        Tuple of (processed_table, preamble_kv):
            processed_table: Processing后的Table, 或 None
            preamble_kv: 从Table header前汇总行Extract的 KV 对 (may为空 dict)
    """
    if not table_data or len(table_data) < 2:
        return table_data, {}

    table_data = normalize_table(table_data)

    # ── 如有 confirmed_header, 先剥离续 table页前置汇总行 ──
    if confirmed_header:
        table_data = _strip_preamble(table_data, confirmed_header)
        if not table_data:
            return None, {}

    # ── 词 tableMatch优先 (BANK_STATEMENT 范围): 在前 10 行中找Match已知列名最多的行 ──
    _CATEGORIES = ["BANK_STATEMENT"]
    header_row_idx = -1
    best_vocab_score = 0
    for i, row in enumerate(table_data[:10]):
        vs = _score_header_by_vocabulary(row, categories=_CATEGORIES)
        if vs > best_vocab_score:
            best_vocab_score = vs
            header_row_idx = i

    # ── Fallback: 结构启发式 ──
    if best_vocab_score < 3:
        header_row_idx = -1
        for i, row in enumerate(table_data[:5]):
            if _is_header_row(row):
                header_row_idx = i
                break
        if header_row_idx == -1:
            for i, row in enumerate(table_data[1:6], 1):
                if _is_data_row(row):
                    header_row_idx = 0
                    break
            if header_row_idx == -1:
                return table_data, {}

    # ── pre-header 行Extract为 KV 元Data (viaReturns值传出, 无GlobalStatus) ──
    preamble_kv: Dict[str, str] = {}
    if header_row_idx > 0:
        preamble_rows = table_data[:header_row_idx]
        preamble_kv = _extract_preamble_kv(preamble_rows)
        if preamble_kv:
            logger.debug(f"[v2] preamble KV extracted: {preamble_kv}")

    header = table_data[header_row_idx]
    data_rows = list(table_data[header_row_idx + 1:])
    # 剥离 header after紧跟着的 preamble 行 (汇总行/重复Table header), 不论 header 在第几行
    data_rows = _strip_preamble(data_rows, header)

    # ── Fix 2: 先Fix粘连Table header, ensure后续 _clean_cell using正确的列名 ──
    try:
        preliminary = [header] + data_rows
        preliminary = _fix_header_by_vocabulary(preliminary)
        header = preliminary[0]
        data_rows = preliminary[1:]
    except Exception as e:
        logger.debug(f"[v2] header fix rollback: {e}")

    # ── 预Filter: remove junk 行和短行, Extract table尾汇总 KV ──
    try:
        clean_rows = []
        tail_junk_rows = []
        for r in data_rows:
            if len(r) < 2:
                continue
            if _is_junk_row(r):
                tail_junk_rows.append(r)
                continue
            clean_rows.append(r)

        # Optimize A: 从 table尾 junk 行 (合计/总计) Extract汇总 KV
        if tail_junk_rows:
            tail_kv = _extract_preamble_kv(tail_junk_rows)
            if tail_kv:
                preamble_kv.update(tail_kv)
                logger.debug(f"[v2] tail summary KV: {tail_kv}")

        data_rows = clean_rows
    except Exception as e:
        logger.debug(f"[v2] junk filter rollback: {e}")

    # ── Fix 3: 统一由 _merge_split_rows Processingall fragment Merge ──
    try:
        merged = _merge_split_rows([header] + data_rows)
        header = merged[0]
        data_rows = merged[1:]
    except Exception as e:
        logger.debug(f"[v2] merge_split rollback: {e}")

    # ── Data行清洗: 列Alignment + 单元格清洗 ──
    result: List[List[str]] = [header]

    for row in data_rows:
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        elif len(row) > len(header):
            row = row[:len(header)]

        try:
            row = [_clean_cell(cell, col_name) for cell, col_name in zip(row, header)]
        except Exception as e:
            logger.debug(f"[v2] clean_cell rollback: {e}")
        result.append(row)

    return result, preamble_kv


def _find_vocab_words_in_string(
    s: str,
    categories: Optional[List[str]] = None,
) -> List[Tuple[str, int, int]]:
    """贪心最长Match: 在字符串中找出all已知Table header词及其位置 (NFKC + 繁简归一化)。

    Args:
        s: 待Match字符串
        categories: 限制Match的 category List; 为 None 时using全量词 table
    """
    s = _normalize_for_vocab(s)
    vocab = (
        frozenset().union(*(VOCAB_BY_CATEGORY.get(c, frozenset()) for c in categories))
        if categories else KNOWN_HEADER_WORDS
    )
    sorted_vocab = sorted(vocab, key=len, reverse=True)

    found: List[Tuple[str, int, int]] = []
    used: set = set()

    for word in sorted_vocab:
        start = 0
        while True:
            idx = s.find(word, start)
            if idx == -1:
                break
            end = idx + len(word)
            if not any(i in used for i in range(idx, end)):
                found.append((word, idx, end))
                used.update(range(idx, end))
            start = idx + 1

    return sorted(found, key=lambda x: x[1])


def _fix_header_by_vocabulary(
    table: List[List[str]],
) -> List[List[str]]:
    """词 table驱动的Table header修正: 只Fix table header列名, 不改变列数和Data行。

    策略: 将Table header拼接后用词 tableMatch找出更多列名,
    然后将Match到的列名按位置顺序填回原有列。
    """
    if not table or len(table) < 2:
        return table

    header = table[0]
    n_cols = len(header)
    old_score = _score_header_by_vocabulary(header)

    concat = "".join((c or "").strip() for c in header)
    if not concat:
        return table

    found = _find_vocab_words_in_string(concat)

    # Guard 1: Match到的词数必须显著多于已有Match (标志粘连)
    min_improvement = max(3, old_score + 3) if old_score >= 3 else old_score * 2 + 1
    if len(found) < min_improvement:
        return table
    # Guard 2: 至少 3 个词Match
    if len(found) < 3:
        return table
    # Guard 3: 词 table词必须override拼接串主体 (≥50%)
    # Note: 用去空格后的长度Calculate, 因为 PDF 中Table header列名间常有大量空格
    concat_nospace = concat.replace(" ", "").replace("\u3000", "")
    covered = sum(end - start for _, start, end in found)
    if covered / max(len(concat_nospace), 1) < 0.5:
        return table

    # 只replaceTable header行, 不动Data行
    new_header = [w for w, _, _ in found]
    if len(new_header) > n_cols:
        new_header = new_header[:n_cols]
    elif len(new_header) < n_cols:
        new_header += header[len(new_header):]

    logger.info(
        f"[v2] vocab header fix: score {old_score}→{len(found)}, "
        f"header {header[:3]}→{new_header[:3]}"
    )

    result = [new_header] + table[1:]
    return result


def _clean_cell(cell: str, col_name: str) -> str:
    """通用单元格清洗 (按列名特征自适应)。"""
    cell = (cell or "").strip()
    if not cell:
        return cell

    col_lower = col_name.lower()

    # ── F-5: Account number/ID 类列Protected — 原样Returns，不做Format化 ──
    _ID_KEYWORDS = ["Account number", "Card number", "序号", "编号", "凭证", "流水号",
                    "Log号", "account", "储种", "地区"]
    if any(kw in col_lower for kw in _ID_KEYWORDS):
        return cell

    # ── F-4: Date时间完整retain ──
    if any(kw in col_lower for kw in ["Date", "时间", "date"]):
        # 先从原始 cell (含空格) Extract时间
        time_match = _RE_TIME.search(cell)

        compact = cell.replace(" ", "")
        date_match = _RE_DATE_HYPHEN.search(compact)
        if not date_match:
            raw_match = _RE_DATE_COMPACT.search(compact)
            if raw_match:
                d = raw_match.group(1)
                date_str = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
                date_match = _RE_DATE_HYPHEN.search(date_str)
                # 尝试从紧凑Date后面Extract HHMMSS (如 20250921162345)
                if not time_match:
                    after_date = compact[raw_match.end():]
                    hhmmss = re.match(r"(\d{2})(\d{2})(\d{2})", after_date)
                    if hhmmss:
                        h, m, s = int(hhmmss.group(1)), int(hhmmss.group(2)), int(hhmmss.group(3))
                        if 0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59:
                            time_match = type('M', (), {'group': lambda self: f"{h:02d}:{m:02d}:{s:02d}"})()

        if date_match:
            # 也尝试从 compact 中找Standard时间Format (HH:MM:SS)
            if not time_match:
                time_match = _RE_TIME.search(compact)
            return f"{date_match.group()} {time_match.group()}" if time_match else date_match.group()

    if any(kw in col_lower for kw in ["Amount", "Balance", "发生", "amount", "balance"]):
        return parse_amount(cell)

    if any(kw in col_lower for kw in ["币", "currency"]):
        cleaned = _RE_ONLY_CJK.sub("", cell)
        return cleaned if cleaned else cell

    return cell


def _merge_split_rows(table: List[List[str]]) -> List[List[str]]:
    """Merge被Split的行 (F-2 增强版)。"""
    if len(table) < 2:
        return table

    # F-2: 页Separator/Comment行正则
    _RE_ANNOTATION = re.compile(
        r"^[-=─—━]{3,}$|接下页|续[上下]?页|第\d+页.*共|page\s*\d+|^[-=]{5,}",
        re.IGNORECASE,
    )
    _RE_SUMMARY = re.compile(r"合计|共计|总计|小计|期末Balance|期初Balance")

    def _row_type(row):
        """判断行Type: 'data', 'fragment', 'junk', 'summary'。"""
        row_text = "".join(str(c or "") for c in row).strip()
        if not row_text:
            return "junk"

        # Comment/分隔行
        if _RE_ANNOTATION.search(row_text):
            return "junk"

        # 合计/汇总行
        if _RE_SUMMARY.search(row_text):
            if re.search(r"打印时间|Print date|操作员", row_text):
                return "junk"
            return "summary"

        first = (row[0] if row else "").strip()
        has_content = any((c or "").strip() for c in row[1:]) if len(row) > 1 else False

        # 空首列 + 有内容 → fragment
        if not first and has_content:
            return "fragment"

        # Date锚定: Bank statement中每笔交易首行必有Date, 无Date = 续行
        has_date = any(_RE_VALID_DATE.search(c or "") for c in row)
        if has_date:
            return "data"

        # Fix 3: AmountDetect — 若行含Amount且第一列非空, 视为独立Data行
        has_amount = any(
            _RE_IS_AMOUNT.match((c or "").strip().replace(",", "").replace("¥", ""))
            for c in row if (c or "").strip()
        )
        if has_amount and first:
            return "data"

        # F-2: 低填充率行 (<50% 列有值) 且无Date → fragment
        filled = sum(1 for c in row if (c or "").strip())
        if filled > 0 and filled < len(row) * 0.5:
            return "fragment"

        has_any = any((c or "").strip() for c in row)
        if has_any:
            return "fragment"

        return "data"

    def _is_header(row):
        return not any(
            any(ch.isdigit() for ch in cell)
            for cell in row if cell.strip()
        )

    def _merge_into(target, source):
        for i, cell in enumerate(source):
            val = (cell or "").strip()
            if val and i < len(target):
                existing = (target[i] or "").strip()
                if existing:
                    target[i] = _smart_join(existing, val)
                else:
                    target[i] = val

    # Pass 1: Filter junk 行 (Comment/Separator)
    filtered = []
    for row in table:
        rt = _row_type(row)
        if rt != "junk":
            filtered.append(row)

    if len(filtered) < 2:
        return filtered if filtered else table

    # Pass 2: 反向扫描 — header 之下的 fragment Merge到下一个Data行
    result = list(filtered)
    i = len(result) - 1
    while i >= 1:
        if _row_type(result[i]) == "fragment":
            j = i - 1
            while j >= 0 and _row_type(result[j]) == "fragment":
                j -= 1
            if j >= 0 and _is_header(result[j]):
                k = i + 1
                while k < len(result) and _row_type(result[k]) == "fragment":
                    k += 1
                if k < len(result) and _row_type(result[k]) == "data":
                    _merge_into(result[k], result[i])
                    result.pop(i)
        i -= 1

    # Pass 3: 正向扫描 — fragment Merge到前一个Data行
    merged = [result[0]]
    seen_data = False
    for row in result[1:]:
        rt = _row_type(row)
        if rt == "fragment":
            if seen_data and merged and not _is_header(merged[-1]):
                _merge_into(merged[-1], row)
            # else: 首条Data行before的 fragment → 丢弃 (跨页残留)
        else:
            if rt in ("data", "summary"):
                seen_data = True
            merged.append(row)

    return merged


def _extract_summary_entities(chars: list, out: dict):
    """从 summary zone 的 chars Extract key-value 对。

    增强: supports同行多 KV 粘连Detect (如 "Account name:XXCurrency:YY")。
    """
    if not chars:
        return

    row_map = defaultdict(list)
    for c in chars:
        y_key = round(c["top"] / 3) * 3
        row_map[y_key].append(c)

    lines = []
    for y_key in sorted(row_map.keys()):
        row_chars = sorted(row_map[y_key], key=lambda c: c["x0"])
        parts = []
        for i, c in enumerate(row_chars):
            if i > 0 and c["x0"] - row_chars[i - 1]["x1"] > 10:
                parts.append("  ")
            parts.append(c["text"])
        lines.append("".join(parts))

    full = "\n".join(lines)
    for segment in re.split(r'\s{2,}|\n', full):
        segment = segment.strip()
        if not segment:
            continue
        _parse_kv_segment(segment, out)


# 常见 KV key 的Mode (中文短词 + 冒号)
_KV_EMBEDDED_RE = re.compile(
    r"([\u4e00-\u9fff]{2,6})"  # 2~6 个中文字符 (key)
    r"[：:]"                    # 冒号Separator
)


def _parse_kv_segment(segment: str, out: dict):
    """Parse单个 segment 为 KV 对, supports同行粘连Detect。

    例e.g.: "Account name:重庆中链农科技有限公司Currency:人民币"
    → Account name=重庆中链农科技有限公司, Currency=人民币
    """
    # 尝试多种Separator: 全角冒号、半角冒号、等号、Tab
    for delim in ["：", ":", "=", "\t"]:
        if delim not in segment:
            continue

        k, v = segment.split(delim, 1)
        k, v = k.strip(), v.strip()
        if not k or not v or len(k) >= 20:
            break

        # ── 检查 v 中Whether嵌入了另一个 KV 对 ──
        # Pass 1: 用已知 KV Keywords精确Match (高精度)
        split_pos = _find_embedded_kv_by_keywords(v)
        if split_pos is None:
            # Pass 2: 扫描all "冒号" 位置, 取冒号前最短的 CJK 词 (泛化)
            split_pos = _find_embedded_kv_by_colon_scan(v)

        if split_pos is not None and split_pos > 0:
            first_value = v[:split_pos].strip()
            rest = v[split_pos:].strip()
            if first_value:
                out[k] = first_value
            if rest:
                _parse_kv_segment(rest, out)
            return

        # 无嵌套, 直接记录
        out[k] = v
        break


# 常见的 KV Keywords (用于精确Match嵌入的 key)
_COMMON_KV_KEYWORDS = [
    "Currency", "Account name", "Account number", "Card number", "Account", "Type", "Date",
    "姓名", "编号", "Status", "备注", "Abstract/Summary", "Amount", "Balance",
    "Bank name", "From/to date", "起始Date", "截止Date", "Print date",
    "总笔数", "总Amount", "Page number", "机构",
]


def _find_embedded_kv_by_keywords(v: str) -> "int | None":
    """用已知Keywords在 value 中查找嵌入的 key:value 对。"""
    best_pos = None
    for kw in _COMMON_KV_KEYWORDS:
        for delim in ["：", ":"]:
            pattern = kw + delim
            idx = v.find(pattern)
            if idx > 0:  # 必须有前面的 value partial
                if best_pos is None or idx > best_pos:
                    best_pos = idx  # 取最靠后的Match
    return best_pos


def _find_embedded_kv_by_colon_scan(v: str) -> "int | None":
    """扫描冒号位置, 检查冒号前Whether有 2~4 个中文字符 (疑似 key)。"""
    best_pos = None
    for delim in ["：", ":"]:
        pos = 0
        while True:
            idx = v.find(delim, pos)
            if idx <= 0:
                break
            # 检查冒号前的中文字符数
            cjk_before = 0
            scan = idx - 1
            while scan >= 0 and '\u4e00' <= v[scan] <= '\u9fff':
                cjk_before += 1
                scan -= 1
            # 2~4 个中文字 + 前面有非中文内容 → may是嵌入的 key
            if 2 <= cjk_before <= 4 and scan >= 0:
                key_start = idx - cjk_before
                if best_pos is None or key_start > best_pos:
                    best_pos = key_start
            pos = idx + 1
    return best_pos
