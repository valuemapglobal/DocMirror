"""
Table Post-processing
======================

Split from ``layout_analysis.py``.  Contains ``post_process_table``,
``_strip_preamble``, ``_fix_header_by_vocabulary``, ``_clean_cell``,
``_merge_split_rows``, ``_extract_summary_entities``, etc.
"""
from __future__ import annotations


import logging
import re
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from ..utils.text_utils import _is_cjk_char, _smart_join, normalize_table, parse_amount, _RE_DATE_COMPACT, _RE_DATE_HYPHEN, _RE_TIME, _RE_ONLY_CJK
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
    """Extract key-value metadata pairs from pre-header rows.

    Rule: adjacent non-empty cells matching a (CJK label, numeric/date value)
    pattern are extracted as KV pairs.  ``None`` cells are skipped first to
    produce a compact cell list.
    """
    kv: Dict[str, str] = {}
    for row in rows:
        # Filter out None / whitespace to get a compact non-empty cell list
        cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
        i = 0
        while i < len(cells) - 1:
            key = cells[i]
            val = cells[i + 1]
            # key: non-empty, contains CJK, not a pure number / date
            # val: non-empty, is an amount / date / pure number
            if (
                key and val
                and re.search(r"[\u4e00-\u9fff]", key)
                and not _RE_IS_DATE.match(key)
                and not _RE_IS_AMOUNT.match(key.replace(",", ""))
            ):
                clean_val = val.replace(",", "").replace("\u00a5", "").replace(" ", "")
                is_num_or_date = bool(
                    _RE_IS_DATE.search(val) or
                    (_RE_IS_AMOUNT.match(clean_val) if clean_val else False)
                )
                if is_num_or_date:
                    kv[key] = val
                    i += 2  # Skip the value cell
                    continue
            i += 1
    return kv


def _strip_preamble(
    rows: List[List[str]],
    confirmed_header: List[str],
    categories: Optional[List[str]] = None,
) -> List[List[str]]:
    """Strip duplicate summary rows and repeated headers from the beginning
    of a continuation-page table.

    Args:
        rows: Rows to filter.
        confirmed_header: The confirmed header row.
        categories: Vocabulary categories for matching; defaults to ``["BANK_STATEMENT"]``.
    """
    if not confirmed_header or not rows:
        return rows

    # Non-empty cells of the confirmed header (normalised)
    header_cells = {
        _normalize_for_vocab(c).strip()
        for c in confirmed_header
        if c and c.strip()
    }

    if not categories:
        categories = ["BANK_STATEMENT"]

    max_scan = min(10, len(rows))

    # Two-phase scan:
    # Phase 1: scan the first max_scan rows; find the last row with vocab_score >= 3
    #          (duplicate header row)
    last_header_idx = -1
    for i in range(max_scan):
        vs = _score_header_by_vocabulary(rows[i], categories=categories)
        if vs >= 3:
            last_header_idx = i

    if last_header_idx >= 0:
        # F-7: strip protection — cap at 5 rows to avoid data loss
        if last_header_idx > 5:
            logger.warning(
                f"strip_preamble: vocab header at row {last_header_idx} "
                f"(> 5 rows) \u2014 capping to avoid data loss"
            )
            last_header_idx = 5
        logger.debug(
            f"strip_preamble: skip rows 0-{last_header_idx} "
            f"(vocab repeated header at row {last_header_idx})"
        )
        return rows[last_header_idx + 1:]

    # Phase 2: no duplicate header found; try header-similarity matching
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
                    f"strip_preamble: skip rows 0-{i} "
                    f"(header overlap={overlap:.2f})"
                )
                return rows[i + 1:]
        # Stop similarity detection once a real data row is encountered
        if _is_data_row(row):
            break

    return rows


# ── Regex patterns for semantic column split ──
_RE_SEQ_PLUS_DESC = re.compile(
    r'^(\d{1,6})'              # Sequence number (1-6 digits)
    r'([^\d\s,.].*)',          # Followed by non-numeric text (the description)
    re.DOTALL,
)
_RE_BALANCE_PLUS_TEXT = re.compile(
    r'^([\d,]+\.\d{2})'       # Amount with 2 decimal places (e.g. 56,264.17)
    r'([^\d\s,.].*)',          # Followed by non-numeric text (remarks)
    re.DOTALL,
)


def _split_merged_columns(
    header: List[str],
    data_rows: List[List[str]],
) -> "Tuple[List[str], List[List[str]]] | None":
    """Semantic column split: detect and repair cells where adjacent columns
    were merged due to narrow spatial gaps in the PDF.

    Detectable patterns:
      1. 序号+摘要 merge: cell = "2851消费" → split into ["2851", "消费"]
      2. 余额+附言 merge: cell = "56,264.17财付通-微信支付" → split into ["56,264.17", "财付通-..."]

    Activation: only triggers when >30% of data rows show the pattern.
    Safety: does nothing for columns that don't match the patterns.

    Returns:
        ``(new_header, new_data_rows)`` if any split was applied, else ``None``.
    """
    if not header or not data_rows or len(data_rows) < 5:
        return None

    n_cols = len(header)
    n_rows = len(data_rows)

    # ── Detect mergeable columns ──
    # For each column, count how many rows have a pattern match
    split_specs = []  # (col_idx, pattern, new_header_left, new_header_right, match_count)

    for ci in range(n_cols):
        h = _normalize_for_vocab(header[ci]) if ci < len(header) else ""

        # Pattern 1: 序号+摘要 — sequence number column with description appended
        if h in ("序号", "交易序号", "编号", "no", "no.", "序列号"):
            match_count = sum(
                1 for r in data_rows
                if ci < len(r) and r[ci] and _RE_SEQ_PLUS_DESC.match(str(r[ci]).strip())
            )
            if match_count > n_rows * 0.3:
                # Find the next column — it should be the empty "摘要" target
                next_empty_ci = None
                for nci in range(ci + 1, n_cols):
                    nh = _normalize_for_vocab(header[nci]) if nci < len(header) else ""
                    empty_count = sum(1 for r in data_rows if nci < len(r) and not (r[nci] or "").strip())
                    if empty_count > n_rows * 0.3 or nh in ("摘要", "交易摘要", "用途", "附言"):
                        next_empty_ci = nci
                        break
                if next_empty_ci is not None:
                    split_specs.append((ci, _RE_SEQ_PLUS_DESC, next_empty_ci))

        # Pattern 2: 余额+附言 — balance amount with remarks appended
        # Look for columns where values look like "56,264.17财付通-微信支付-每天数独"
        # Trigger: check ANY column for this pattern (not just specific headers)
        match_count = sum(
            1 for r in data_rows
            if ci < len(r) and r[ci] and _RE_BALANCE_PLUS_TEXT.match(str(r[ci]).strip())
        )
        if match_count > n_rows * 0.3:
            # The balance portion should go to the PREVIOUS column (if mostly empty)
            prev_ci = ci - 1
            if prev_ci >= 0:
                prev_empty = sum(1 for r in data_rows if prev_ci < len(r) and not (r[prev_ci] or "").strip())
                if prev_empty > n_rows * 0.3:
                    split_specs.append((ci, _RE_BALANCE_PLUS_TEXT, -(prev_ci)))

    if not split_specs:
        return None

    # ── Apply splits ──
    modified = False
    new_data_rows = []

    for row in data_rows:
        new_row = list(row)
        # Pad to header length
        while len(new_row) < n_cols:
            new_row.append("")

        for ci, pattern, target_ci in split_specs:
            if ci >= len(new_row):
                continue
            cell = str(new_row[ci] or "").strip()
            if not cell:
                continue

            m = pattern.match(cell)
            if not m:
                continue

            left_part = m.group(1).strip()
            right_part = m.group(2).strip()

            if target_ci < 0:
                # Balance+text: balance goes to previous column, text stays
                prev_ci = -target_ci
                if prev_ci < len(new_row) and not (new_row[prev_ci] or "").strip():
                    new_row[prev_ci] = left_part
                    new_row[ci] = right_part
                    modified = True
            else:
                # Seq+desc: sequence stays, description goes to next column
                if target_ci < len(new_row) and not (new_row[target_ci] or "").strip():
                    new_row[ci] = left_part
                    new_row[target_ci] = right_part
                    modified = True

        new_data_rows.append(new_row)

    if not modified:
        return None

    # Count how many rows were actually split
    split_count = sum(
        1 for orig, new in zip(data_rows, new_data_rows)
        if orig != new
    )
    logger.info(f"semantic column split: repaired {split_count}/{n_rows} rows")

    return header, new_data_rows


def post_process_table(
    table_data: List[List[str]],
    confirmed_header: Optional[List[str]] = None,
) -> Tuple[Optional[List[List[str]]], Dict[str, str]]:
    """General-purpose table post-processing \u2014 keyword-independent.

    Args:
        table_data: Raw 2-D table.
        confirmed_header: Confirmed header (used for continuation-page preamble stripping).

    Returns:
        ``(processed_table, preamble_kv)``:
            processed_table: post-processed table, or ``None``.
            preamble_kv: KV pairs extracted from pre-header summary rows (may be empty).
    """
    if not table_data or len(table_data) < 2:
        return table_data, {}

    table_data = normalize_table(table_data)

    # ── If confirmed_header exists, strip continuation-page preamble rows ──
    if confirmed_header:
        table_data = _strip_preamble(table_data, confirmed_header)
        if not table_data:
            return None, {}

    # ── Vocabulary match priority (BANK_STATEMENT scope): find the row in the first 10
    #    that matches the most known column names ──
    _CATEGORIES = ["BANK_STATEMENT"]
    header_row_idx = -1
    best_vocab_score = 0
    for i, row in enumerate(table_data[:10]):
        vs = _score_header_by_vocabulary(row, categories=_CATEGORIES)
        if vs > best_vocab_score:
            best_vocab_score = vs
            header_row_idx = i

    # ── Fallback: structural heuristic ──
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

    # ── Extract pre-header rows as KV metadata (returned, no global state) ──
    preamble_kv: Dict[str, str] = {}
    if header_row_idx > 0:
        preamble_rows = table_data[:header_row_idx]
        preamble_kv = _extract_preamble_kv(preamble_rows)
        if preamble_kv:
            logger.debug(f"preamble KV extracted: {preamble_kv}")

    header = table_data[header_row_idx]
    data_rows = list(table_data[header_row_idx + 1:])

    # ── Multi-row header merge: detect sub-header rows that refine spanning parent cells ──
    # Pattern: Parent  = ["Txn Date",  "Serial#",  "Amount",    "",      "Balance", "Cpty Info",  "",         "Summary", "Remarks"]
    #          Sub-hdr = ["",          "",         "Debit",     "Credit", "",        "Cpty Bank",  "Cpty Name", "",       ""]
    # → Merged: ["Txn Date",  "Serial#",  "Debit",     "Credit", "Balance", "Cpty Bank",  "Cpty Name", "Summary", "Remarks"]
    #
    # Generalized detection:
    #   1. Not a data row (no dates/amounts).
    #   2. Looks header-like (vocab match or _is_header_row).
    #   3. At least one filled cell fills an EMPTY parent position (proves it's a sub-header, not data).
    # Merge strategy: sub-header cells override parent at ALL positions (leaf-level wins over span).
    if data_rows:
        candidate = data_rows[0]
        empty_in_header = {i for i, c in enumerate(header) if not (c or "").strip()}
        filled_in_candidate = {
            i for i, c in enumerate(candidate)
            if i < len(candidate) and (c or "").strip()
        }
        # Must fill at least one empty parent cell AND not be a data row
        fills_empty = filled_in_candidate & empty_in_header
        candidate_is_header_like = (
            _is_header_row(candidate)
            or _score_header_by_vocabulary(candidate) >= 1
        )
        if (
            fills_empty
            and candidate_is_header_like
            and not _is_data_row(candidate)
        ):
            merged_header = list(header)
            for i in filled_in_candidate:
                if i < len(merged_header):
                    merged_header[i] = (candidate[i] or "").strip()
            logger.info(
                f"multi-row header merge: {len(fills_empty)} gap-fills + "
                f"{len(filled_in_candidate - empty_in_header)} span-refinements"
            )
            header = merged_header
            data_rows = data_rows[1:]


    # Strip preamble rows immediately after the header (summary / duplicate header),
    # regardless of which row the header is on
    data_rows = _strip_preamble(data_rows, header)

    # ── Fix 2: fix concatenated headers first, ensuring _clean_cell uses correct column names ──
    try:
        preliminary = [header] + data_rows
        preliminary = _fix_header_by_vocabulary(preliminary)
        header = preliminary[0]
        data_rows = preliminary[1:]
    except Exception as e:
        logger.debug(f"header fix rollback: {e}")

    # ── Pre-filter: remove junk rows and short rows, extract tail-summary KV ──
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

        # Optimisation A: extract summary KV from tail junk rows (totals)
        if tail_junk_rows:
            tail_kv = _extract_preamble_kv(tail_junk_rows)
            if tail_kv:
                preamble_kv.update(tail_kv)
                logger.debug(f"tail summary KV: {tail_kv}")

        data_rows = clean_rows
    except Exception as e:
        logger.debug(f"junk filter rollback: {e}")

    # ── Fix 3: unified fragment merging via _merge_split_rows ──
    try:
        merged = _merge_split_rows([header] + data_rows)
        header = merged[0]
        data_rows = merged[1:]
    except Exception as e:
        logger.debug(f"merge_split rollback: {e}")

    # ── Fix 4: semantic column split — repair cells where adjacent columns ──
    #    were merged due to tiny spatial gaps (e.g. CCB: 序号+摘要, 余额+附言)
    try:
        split_result = _split_merged_columns(header, data_rows)
        if split_result is not None:
            header, data_rows = split_result
    except Exception as e:
        logger.debug(f"split_merged rollback: {e}")

    # ── Fix 5: split number repair (cross-column digit overflow) ──
    # When right-aligned numbers span beyond their column boundary,
    # the engine splits them: cell N gets a trailing fragment like '5,'
    # and cell N+1 gets the remainder like '000,888.02'.  Detect and
    # reassemble such split numbers.
    _RE_TRAILING_FRAG = re.compile(r'(\s+)(\d{1,3},)$')
    for row in data_rows:
        for j in range(len(row) - 1):
            cell = (row[j] or "").strip()
            next_cell = (row[j + 1] or "").strip()
            if not cell or not next_cell:
                continue
            if not re.match(r'\d', next_cell):
                continue
            # Case 1: entire cell is a fragment (e.g. '5,' or '12,')
            if re.fullmatch(r'\d{1,3},', cell):
                row[j] = ""
                row[j + 1] = cell + next_cell
                continue
            # Case 2: cell ends with ' 1,' (trailing fragment after space)
            m = _RE_TRAILING_FRAG.search(cell)
            if m:
                tail = m.group(2)
                row[j] = cell[:m.start()].strip()
                row[j + 1] = tail + next_cell

    # ── Data row cleaning: column alignment + cell cleaning ──
    result: List[List[str]] = [header]

    for row in data_rows:
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        elif len(row) > len(header):
            row = row[:len(header)]

        try:
            row = [_clean_cell(cell, col_name) for cell, col_name in zip(row, header)]
        except Exception as e:
            logger.debug(f"clean_cell rollback: {e}")
        result.append(row)

    return result, preamble_kv


def _find_vocab_words_in_string(
    s: str,
    categories: Optional[List[str]] = None,
) -> List[Tuple[str, int, int]]:
    """Greedy longest-match: find all known header words and their positions
    in a string (NFKC + simplified/traditional Chinese normalisation).

    Args:
        s: String to search.
        categories: Restrict matching to these category lists; ``None`` uses the full vocabulary.
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
    """Vocabulary-driven header correction: fix concatenated column names
    without changing the column count or data rows.

    Strategy: concatenate all header cells, then use vocabulary matching
    to find more column names; fill the matched names back into the
    original columns in positional order.
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

    # Guard 1: matched word count must significantly exceed existing matches (indicates concatenation)
    min_improvement = max(3, old_score + 3) if old_score >= 3 else old_score * 2 + 1
    if len(found) <= min_improvement:
        return table
    # Guard 2: at least 3 vocabulary matches
    if len(found) < 3:
        return table
    # Guard 3: vocabulary words must cover >= 50 % of the concatenated string
    # Note: use de-spaced length since PDF headers often have large inter-column spaces
    concat_nospace = concat.replace(" ", "").replace("\u3000", "")
    covered = sum(end - start for _, start, end in found)
    if covered / max(len(concat_nospace), 1) < 0.5:
        return table

    # Replace header row only; data rows are untouched
    new_header = [w for w, _, _ in found]
    if len(new_header) > n_cols:
        new_header = new_header[:n_cols]
    elif len(new_header) < n_cols:
        new_header += header[len(new_header):]

    logger.info(
        f"vocab header fix: score {old_score}\u2192{len(found)}, "
        f"header {header[:3]}\u2192{new_header[:3]}"
    )

    result = [new_header] + table[1:]
    return result


def _clean_cell(cell: str, col_name: str) -> str:
    """General-purpose cell cleaning (adaptive to column-name features)."""
    cell = (cell or "").strip()
    if not cell:
        return cell

    col_lower = col_name.lower()

    # ── F-5: account-number / ID columns — return as-is, no formatting ──
    _ID_KEYWORDS = ["\u8d26\u53f7", "\u5361\u53f7", "\u5e8f\u53f7", "\u7f16\u53f7", "\u51ed\u8bc1", "\u6d41\u6c34\u53f7",
                    "\u65e5\u5fd7\u53f7", "account", "\u50a8\u79cd", "\u5730\u533a"]
    if any(kw in col_lower for kw in _ID_KEYWORDS):
        return cell

    # ── F-4: date-time columns — preserve complete date and time ──
    if any(kw in col_lower for kw in ["\u65e5\u671f", "\u65f6\u95f4", "date"]):
        # Extract time from the original cell (including spaces)
        time_match = _RE_TIME.search(cell)

        compact = cell.replace(" ", "")
        date_match = _RE_DATE_HYPHEN.search(compact)
        if not date_match:
            raw_match = _RE_DATE_COMPACT.search(compact)
            if raw_match:
                d = raw_match.group(1)
                date_str = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
                date_match = _RE_DATE_HYPHEN.search(date_str)
                # Try extracting HHMMSS from after the compact date (e.g. 20250921162345)
                if not time_match:
                    after_date = compact[raw_match.end():]
                    hhmmss = re.match(r"(\d{2})(\d{2})(\d{2})", after_date)
                    if hhmmss:
                        h, m, s = int(hhmmss.group(1)), int(hhmmss.group(2)), int(hhmmss.group(3))
                        if 0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59:
                            time_match = type('M', (), {'group': lambda self: f"{h:02d}:{m:02d}:{s:02d}"})()\

        if date_match:
            # Also try finding standard time format (HH:MM:SS) from compact string
            if not time_match:
                time_match = _RE_TIME.search(compact)
            return f"{date_match.group()} {time_match.group()}" if time_match else date_match.group()

    if any(kw in col_lower for kw in ["\u91d1\u989d", "\u4f59\u989d", "\u53d1\u751f", "amount", "balance"]):
        return parse_amount(cell)

    if any(kw in col_lower for kw in ["\u5e01", "currency"]):
        cleaned = _RE_ONLY_CJK.sub("", cell)
        return cleaned if cleaned else cell

    return cell


def _merge_split_rows(table: List[List[str]]) -> List[List[str]]:
    """Merge rows that were split across lines (F-2 enhanced version)."""
    if len(table) < 2:
        return table

    # F-2: page separator / annotation row regex
    _RE_ANNOTATION = re.compile(
        r"^[-=\u2500\u2014\u2501]{3,}$|\u63a5\u4e0b\u9875|\u7eed[\u4e0a\u4e0b]?\u9875|\u7b2c\d+\u9875.*\u5171|page\s*\d+|^[-=]{5,}",
        re.IGNORECASE,
    )
    _RE_SUMMARY = re.compile(r"\u5408\u8ba1|\u5171\u8ba1|\u603b\u8ba1|\u5c0f\u8ba1|\u671f\u672b\u4f59\u989d|\u671f\u521d\u4f59\u989d")

    def _row_type(row):
        """Determine row type: 'data', 'fragment', 'junk', or 'summary'."""
        row_text = "".join(str(c or "") for c in row).strip()
        if not row_text:
            return "junk"

        # Annotation / separator row
        if _RE_ANNOTATION.search(row_text):
            return "junk"

        # Summary / totals row
        if _RE_SUMMARY.search(row_text):
            if re.search(r"\u6253\u5370\u65f6\u95f4|Print date|\u64cd\u4f5c\u5458", row_text):
                return "junk"
            return "summary"

        first = (row[0] if row else "").strip()
        has_content = any((c or "").strip() for c in row[1:]) if len(row) > 1 else False

        # Empty first column + has content → fragment
        if not first and has_content:
            return "fragment"

        # Date anchor: every bank-statement transaction starts with a date; no date = continuation
        has_date = any(_RE_VALID_DATE.search(c or "") for c in row)
        if has_date:
            return "data"

        # Fix 3: amount detection — if row has amounts and first cell is non-empty, treat as data
        has_amount = any(
            _RE_IS_AMOUNT.match((c or "").strip().replace(",", "").replace("\u00a5", ""))
            for c in row if (c or "").strip()
        )
        if has_amount and first:
            return "data"

        # F-2: low fill-rate row (< 50 % columns filled) with no date → fragment
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

    # Pass 1: filter junk rows (annotations / separators)
    filtered = []
    for row in table:
        rt = _row_type(row)
        if rt != "junk":
            filtered.append(row)

    if len(filtered) < 2:
        return filtered if filtered else table

    # Pass 2: reverse scan — fragments below the header merge into the next data row
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

    # Pass 3: complementary column merge (staggered y-layout fix)
    # In borderless tables (e.g. 富滇银行), the left-half and right-half of
    # a single logical row may sit at slightly different y-positions, causing
    # the engine to split them into separate rows.  Merge when filled columns
    # have ZERO overlap (strictest possible condition — no false positives).
    i = 0
    while i < len(result) - 1:
        rt_i = _row_type(result[i])
        rt_next = _row_type(result[i + 1])
        if rt_i == "fragment" and rt_next in ("data", "fragment"):
            filled_i = {j for j, c in enumerate(result[i]) if (c or "").strip()}
            filled_next = {j for j, c in enumerate(result[i + 1]) if (c or "").strip()}
            if filled_i and filled_next and not (filled_i & filled_next):
                # For single-column, short-content fragments (e.g. '園' in col6,
                # '店', '司'), check if the PRECEDING row has content in that
                # column — if so, this is a wrapped-char overflow, not a
                # complement.  Long single-column values (e.g. a full merchant
                # name) are treated as genuine complements.
                if len(filled_i) == 1 and i > 0:
                    col_idx = next(iter(filled_i))
                    frag_text = (result[i][col_idx] or "").strip()
                    if len(frag_text) <= 3:
                        prev_filled = {j for j, c in enumerate(result[i - 1]) if (c or "").strip()}
                        if filled_i & prev_filled:
                            i += 1
                            continue  # skip — let Pass 4 merge into preceding row
                _merge_into(result[i + 1], result[i])
                result.pop(i)
                continue
        i += 1

    # Pass 4: forward scan — fragments merge into the preceding data row
    merged = [result[0]]
    seen_data = False
    for row in result[1:]:
        rt = _row_type(row)
        if rt == "fragment":
            if seen_data and merged and not _is_header(merged[-1]):
                # Overlap guard: if a substantial fragment's filled columns
                # mostly overlap the preceding row, it likely starts the NEXT
                # transaction (staggered y-layout), not a continuation.
                frag_cols = {j for j, c in enumerate(row) if (c or "").strip()}
                prev_cols = {j for j, c in enumerate(merged[-1]) if (c or "").strip()}
                overlap = frag_cols & prev_cols
                if len(frag_cols) >= 3 and len(overlap) > len(frag_cols) * 0.5:
                    merged.append(row)
                else:
                    _merge_into(merged[-1], row)
            # else: fragments before the first data row → discard (cross-page residue)
        else:
            if rt in ("data", "summary"):
                seen_data = True
            merged.append(row)

    return merged


def _extract_summary_entities(chars: list, out: dict):
    """Extract key-value pairs from characters in a summary zone.

    Enhancement: supports same-line multi-KV concatenation detection
    (e.g. "Account name:XX Currency:YY").
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


# Common KV key pattern (short CJK word + colon)
_KV_EMBEDDED_RE = re.compile(
    r"([\u4e00-\u9fff]{2,6})"  # 2\u20136 CJK characters (key)
    r"[\uff1a:]"                # Colon separator
)


def _parse_kv_segment(segment: str, out: dict):
    """Parse a single segment into a KV pair; supports same-line
    concatenation detection.

    Example: "Account name:\u91cd\u5e86\u4e2d\u94fe\u519c\u79d1\u6280\u6709\u9650\u516c\u53f8Currency:\u4eba\u6c11\u5e01"
    \u2192 Account name=\u91cd\u5e86\u4e2d\u94fe\u519c\u79d1\u6280\u6709\u9650\u516c\u53f8, Currency=\u4eba\u6c11\u5e01
    """
    # Try multiple separators: full-width colon, half-width colon, equals, tab
    for delim in ["\uff1a", ":", "=", "\t"]:
        if delim not in segment:
            continue

        k, v = segment.split(delim, 1)
        k, v = k.strip(), v.strip()
        if not k or not v or len(k) >= 20:
            break

        # ── Check whether v contains an embedded KV pair ──
        # Pass 1: precise match using known KV keywords (high precision)
        split_pos = _find_embedded_kv_by_keywords(v)
        if split_pos is None:
            # Pass 2: scan all colon positions, take the shortest CJK word before a colon (generalised)
            split_pos = _find_embedded_kv_by_colon_scan(v)

        if split_pos is not None and split_pos > 0:
            first_value = v[:split_pos].strip()
            rest = v[split_pos:].strip()
            if first_value:
                out[k] = first_value
            if rest:
                _parse_kv_segment(rest, out)
            return

        # No embedding — record directly
        out[k] = v
        break


# Common KV keywords (for precise matching of embedded keys)
_COMMON_KV_KEYWORDS = [
    "\u5e01\u79cd", "\u6237\u540d", "\u8d26\u53f7", "\u5361\u53f7", "\u8d26\u6237", "\u7c7b\u578b", "\u65e5\u671f",
    "\u59d3\u540d", "\u7f16\u53f7", "\u72b6\u6001", "\u5907\u6ce8", "\u6458\u8981", "\u91d1\u989d", "\u4f59\u989d",
    "\u884c\u540d", "\u8d77\u6b62\u65e5\u671f", "\u8d77\u59cb\u65e5\u671f", "\u622a\u6b62\u65e5\u671f", "\u7ec8\u6b62\u65e5\u671f", "\u6253\u5370\u65e5\u671f",
    "\u603b\u7b14\u6570", "\u603b\u91d1\u989d", "\u9875\u7801", "\u673a\u6784",
]


def _find_embedded_kv_by_keywords(v: str) -> "int | None":
    """Find an embedded key:value pair in a value string using known keywords.

    Returns the leftmost match position, preferring longer keywords to avoid
    partial substring matches (e.g. '终止日期' over '日期').
    """
    best_pos = None
    best_kw_len = 0
    # Sort longest-first so longer keywords get priority at same position
    for kw in sorted(_COMMON_KV_KEYWORDS, key=len, reverse=True):
        for delim in ["\uff1a", ":"]:
            pattern = kw + delim
            idx = v.find(pattern)
            if idx > 0:  # Must have preceding value content
                # Take leftmost match; at same position prefer longer keyword
                if best_pos is None or idx < best_pos or (idx == best_pos and len(kw) > best_kw_len):
                    best_pos = idx
                    best_kw_len = len(kw)
    return best_pos


def _find_embedded_kv_by_colon_scan(v: str) -> "int | None":
    """Scan colon positions and check whether 2\u20134 CJK characters precede
    the colon (suspected embedded key)."""
    best_pos = None
    for delim in ["\uff1a", ":"]:
        pos = 0
        while True:
            idx = v.find(delim, pos)
            if idx <= 0:
                break
            # Count CJK characters before the colon
            cjk_before = 0
            scan = idx - 1
            while scan >= 0 and '\u4e00' <= v[scan] <= '\u9fff':
                cjk_before += 1
                scan -= 1
            # 2\u20134 CJK chars + preceding non-CJK content \u2192 possibly an embedded key
            if 2 <= cjk_before <= 4 and scan >= 0:
                key_start = idx - cjk_before
                if best_pos is None or key_start > best_pos:
                    best_pos = key_start
            pos = idx + 1
    return best_pos
