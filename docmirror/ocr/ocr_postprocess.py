# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
OCR postprocess — text normalization after recognition.

Purpose: Fixes common OCR errors in amounts, dates, domain terms, and digit
noise using Levenshtein and rule-based correctors.

Main components: ``normalize_chars``, ``fix_amount_format``, ``fix_date_format``,
``fix_domain_terms``.

Upstream: Raw OCR strings from any engine.

Downstream: ``ocr.postprocess.column_aware``, ``table.ocr_scoring``.
"""

from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 1: Character-level normalisation (safest — no ambiguity)
# ═══════════════════════════════════════════════════════════════════════════════

# Full-width → half-width mapping (common OCR artefact)
_FULLWIDTH_MAP = str.maketrans(
    "０１２３４５６７８９"
    "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
    "，。：；（）【】",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz,.：;()[]",
)


def normalize_chars(text: str) -> str:
    """Character-level normalisation: full-width → half-width, NFKC, control character clean-up."""
    # Unicode NFKC normalisation
    text = unicodedata.normalize("NFKC", text)
    # Full-width digits/letters → half-width
    text = text.translate(_FULLWIDTH_MAP)
    # Zero-width / control characters
    text = re.sub(r"[\u200b-\u200f\u2028-\u202f\ufeff]", "", text)
    # Collapse multiple whitespace characters
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 2: Amount format fixing
# ═══════════════════════════════════════════════════════════════════════════════

# Pre-compiled regex patterns (one-time compilation)
_AMOUNT_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # "-230: 43" → "-230.43" (colon + space → decimal point)
    (re.compile(r"([+-]?\d[\d,]*): (\d{2})\b"), r"\1.\2", "colon_space→dot"),
    # "132.995:40" → "132,995.40" (colon → decimal, fix thousands separator)
    (re.compile(r"(\d{1,3})\.(\d{3}):(\d{2})\b"), r"\1,\2.\3", "dot_colon→comma_dot"),
    # "-15;324.55" → "-15,324.55" (semicolon → thousands comma)
    (re.compile(r"([+-]?\d{1,3});(\d{3}[.\d]*)"), r"\1,\2", "semicolon→comma"),
    # "15,458-75" → "15,458.75" (hyphen in decimal position → decimal point)
    (re.compile(r"(\d{3})-(\d{2})\b"), r"\1.\2", "hyphen→decimal"),
    # "-3. 290. 46" → "-3,290.46" (spaced dots → thousands separator)
    (re.compile(r"(\d)\. (\d{3})\. (\d{2})\b"), r"\1,\2.\3", "spaced_dots→amount"),
    # Variant of spaced dots: "4. 088. 31"
    (re.compile(r"(\d)\. (\d{3})\. (\d{2})"), r"\1,\2.\3", "spaced_dots_v2"),
    # ".4,088.31" → "4,088.31" (spurious leading dot)
    (re.compile(r"^\.(\d{1,3},\d{3}\.\d{2})"), r"\1", "leading_dot"),
    # "+4;400.00" → "+4,400.00"
    (re.compile(r"([+-]?\d{1,3});(\d{3}\.\d{2})"), r"\1,\2", "semicolon_amount"),
    # Spurious space in amount: "1, 234. 56" → "1,234.56"
    (re.compile(r"(\d), (\d{3})"), r"\1,\2", "comma_space"),
    (re.compile(r"(\d)\. (\d{2})\b"), r"\1.\2", "dot_space_decimal"),
]


def fix_amount_format(text: str) -> str:
    """Fix punctuation confusion in OCR-recognised amounts."""
    for pattern, replacement, _name in _AMOUNT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 3: Date format fixing
# ═══════════════════════════════════════════════════════════════════════════════

_DATE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # "2024~08-05" → "2024-08-05" (tilde → hyphen)
    (re.compile(r"(\d{4})[~～](\d{2})[-~～]?(\d{2})"), r"\1-\2-\3"),
    # "2024 -08-05" → "2024-08-05" (space + dash variants)
    (re.compile(r"(\d{4})\s*[-–—]\s*(\d{2})\s*[-–—]\s*(\d{2})"), r"\1-\2-\3"),
    # "2024.08.05" → "2024-08-05" (dot-separated date)
    (re.compile(r"(\d{4})\.(\d{2})\.(\d{2})"), r"\1-\2-\3"),
    # "2024/08/05" is kept as-is (valid format)
]


def fix_date_format(text: str) -> str:
    """Fix FormatError in OCR Date."""
    for pattern, replacement in _DATE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 4: Domain dictionary correction (generic version)
# ═══════════════════════════════════════════════════════════════════════════════

# Generic high-frequency OCR glyph-confusion dictionary
# key: incorrect form, value: correct form
# Design: only includes high-frequency unambiguous corrections
_GENERIC_CORRECTIONS: dict[str, str] = {
    # ── Account types (banking, generic) ──
    "活川": "活期",
    "活圳": "活期",
    "活助": "活期",
    "活斯": "活期",
    "活州": "活期",
    "活朋": "活期",
    "定册": "定期",
    "定朋": "定期",
    # ── Payment channels (generic) ──
    "快提支付": "快捷支付",
    "块捷支付": "快捷支付",
    "快措支付": "快捷支付",
    "快据支付": "快捷支付",
    # ── Transaction types (generic) ──
    "转帐": "转账",
    "转帖": "转账",
    "汇入汇": "汇入",
    "他行汇人": "他行汇入",
    "跨行转人": "跨行转入",
    "跨行转人账": "跨行转入",
    "网上银行": "网上银行",  # keep (already correct)
    # ── Currency / general ──
    "人民帀": "人民币",
    "人民巾": "人民币",
    "借记卞": "借记卡",
    "借记下": "借记卡",
    # ── Common verb confusions ──
    "消赀": "消费",
    "消贵": "消费",
    "还歉": "还款",
}

# Payment company name correction (Generic format)
_COMPANY_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Character confusion: "富发支付" -> "富友支付"
    (re.compile(r"富发支付"), "富友支付"),
    # Character confusion: "高友支付" -> "富友支付"
    (re.compile(r"高友支付"), "富友支付"),
    # Character confusion: "通联支忖" -> "通联支付"
    (re.compile(r"支忖"), "支付"),
    (re.compile(r"支村"), "支付"),
]


def fix_domain_terms(text: str) -> str:
    """Fix vetted domain terms through the shared safe-correction engine."""
    from docmirror.ocr.correction import CorrectionContext, SafeOCRCorrector

    decision = SafeOCRCorrector().correct(text, CorrectionContext(role="unknown", mode="safe"))
    return decision.output_text


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 5: Digit noise clean-up (fix pure digit strings)
# ═══════════════════════════════════════════════════════════════════════════════

_DIGIT_CLEANUP: list[tuple[re.Pattern, str]] = [
    # "00000," → "00000" (trailing comma)
    (re.compile(r"(\d{5}),\s*$"), r"\1"),
    # "00:00002+" → cannot be fixed, mark as low confidence (no replacement)
]


def fix_digit_noise(text: str) -> str:
    """Clean OCR noise in pure digit strings."""
    for pattern, replacement in _DIGIT_CLEANUP:
        text = pattern.sub(replacement, text)
    return text


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 6: Levenshtein dictionary correction for standard keys
# ═══════════════════════════════════════════════════════════════════════════════

# Standard, high-value document keys (Property, Business License, etc.)
_STANDARD_KEYS = [
    "不动产单元号",
    "权利类型",
    "权利性质",
    "用途",
    "面积",
    "使用期限",
    "权利其他状况",
    "附记",
    "坐落",
    "权利人",
    "共有情况",
    "法定代表人",
    "注册资本",
    "成立日期",
    "营业期限",
    "经营范围",
    "统一社会信用代码",
    "宗地面积",
    "房屋结构",
    "建筑面积",
]


def _levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def fix_domain_keys(text: str) -> str:
    """Correct short field labels through the shared contextual lexicon."""
    if len(text) > 25:
        return text
    from docmirror.ocr.correction import CorrectionContext, SafeOCRCorrector

    decision = SafeOCRCorrector().correct(text, CorrectionContext(role="field_label", mode="safe"))
    return decision.output_text


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 7: Alphanumeric Substitution (Heuristic Context Constraints)
# ═══════════════════════════════════════════════════════════════════════════════

# Fix typical character/digit confusions based on surrounding context.
# E.g., '0' inside a word should be 'O', 'O' inside a number should be '0'.
_ALPHANUM_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # 0 vs O/o
    # 'O' or 'o' surrounded by digits becomes '0'
    (re.compile(r"(?<=\d)[Oo](?=\d)"), "0", "O_in_digits"),
    # 'O' or 'o' after a currency symbol or trailing a number: "￥10O" -> "￥100", "50o" -> "500"
    (re.compile(r"(?<=\d)[Oo](?P<end>[.,\s]|$)"), r"0\g<end>", "O_at_end_of_digits"),
    # '0' surrounded by letters becomes 'O'
    (re.compile(r"(?<=[a-zA-Z])0(?=[a-zA-Z])"), "O", "0_in_letters"),
    # 1 vs I/l
    # 'l' or 'I' surrounded by digits becomes '1'
    (re.compile(r"(?<=\d)[Il](?=\d)"), "1", "I_in_digits"),
    # '1' surrounded by letters becomes 'l'
    (re.compile(r"(?<=[a-z])1(?=[a-z])"), "l", "1_in_letters"),
    (re.compile(r"(?<=[A-Z])1(?=[A-Z])"), "I", "1_in_upper_letters"),
    # 5 vs S
    # 'S' or 's' surrounded by numbers
    (re.compile(r"(?<=\d)[Ss](?=\d)"), "5", "S_in_digits"),
    # '5' surrounded by letters
    (re.compile(r"(?<=[a-zA-Z])5(?=[a-zA-Z])"), "S", "5_in_letters"),
    # Currency bounds: 'S' right before digits (often from $ or 5)
    (re.compile(r"^S(?=\d{2,})"), "5", "S_at_start_of_digits"),
]


def fix_alphanumeric_confusion(text: str) -> str:
    """Fix common OCR confusions (0/O, 1/l/I, 5/S) using surrounding context constraints."""
    for pattern, replacement, _ in _ALPHANUM_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ═══════════════════════════════════════════════════════════════════════════════
# Unified entry point: full-pipeline post-processing
# ═══════════════════════════════════════════════════════════════════════════════


def postprocess_ocr_text(text: str) -> str:
    """OCR text full pipeline Post-processing.

    Layered execution:
        L1: Character-level cleaning (Full-width to Half-width, NFKC)
        L2: Amount format fix
        L3: Date format fix
        L4: Context-scoped safe dictionary correction
        L5: Digit noise clean

    Fuzzy field-label and typed alphanumeric correction require an explicit
    column/field context and are intentionally not applied to unknown text.
    """
    if not text or not text.strip():
        return text

    text = normalize_chars(text)  # L1
    text = fix_amount_format(text)  # L2
    text = fix_date_format(text)  # L3
    text = fix_domain_terms(text)  # L4 — shared safe engine
    text = fix_digit_noise(text)  # L5

    return text


def postprocess_table(
    table: list[list[str]],
) -> list[list[str]]:
    """Apply OCR post-processing to every cell in a table.

    Args:
        table: Table data (2-D list of strings).

    Returns:
        Corrected table.
    """
    return [[postprocess_ocr_text(cell) if isinstance(cell, str) else cell for cell in row] for row in table]


def postprocess_ocr_result(
    result: dict | None,
) -> dict | None:
    """Apply post-processing to the full result from ``analyze_scanned_page()``.

    Args:
        result: ``{'table': [[...]], 'header_text': str, 'footer_text': str}``

    Returns:
        Corrected result (modified in-place).
    """
    if not result:
        return result

    # Correct table cells
    if "table" in result and result["table"]:
        result["table"] = postprocess_table(result["table"])

    # Correct multiple tables
    if "tables" in result and result["tables"]:
        result["tables"] = [postprocess_table(t) for t in result["tables"]]

    # Correct header / footer text
    if "header_text" in result:
        result["header_text"] = postprocess_ocr_text(result["header_text"])
    if "footer_text" in result:
        result["footer_text"] = postprocess_ocr_text(result["footer_text"])

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# GA1.0-05: Context-Aware Post-Processing — Column-Adaptive Correction
# ═══════════════════════════════════════════════════════════════════════════════


import re as _re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# ── Default column-specific correction chains ─────────────────────────────
# Each chain is a list of callable names (module-level function names) that
# are looked up at init time from the module scope.  This avoids circular
# dependency while keeping the chains declarative.

_COLUMN_CORRECTION_CHAINS: dict[str, list[str]] = {
    "amount": ["normalize_chars", "fix_amount_format", "fix_alphanumeric_confusion"],
    "date": ["normalize_chars", "fix_date_format", "fix_alphanumeric_confusion"],
    "account": ["normalize_chars", "fix_digit_noise"],
    "name": ["normalize_chars", "fix_domain_terms"],
    "code": ["normalize_chars"],
    "text": ["normalize_chars", "fix_domain_terms", "fix_domain_keys"],
    "unknown": ["postprocess_ocr_text"],  # Full 7-layer pipeline fallback
}

# ── Column type inference ──────────────────────────────────────────────────

# Header text patterns → column type
_HEADER_PATTERNS: list[tuple[_re.Pattern, str]] = [
    (_re.compile(r"金额|价款|币种|小写|大写|合计|总计|¥|￥|\$|€|£"), "amount"),
    (_re.compile(r"日期|时间|年月日|年\s*月\s*日|期限|到期|起息|交易日"), "date"),
    (_re.compile(r"账号|卡号|户号|编号|代码|证号|信用代码|登记号"), "account"),
    (_re.compile(r"名称|户名|单位|公司|企业|客户|权利人|所有人|姓名"), "name"),
    (_re.compile(r"摘要|用途|附言|备注|说明|事由|类型|性质|用途"), "text"),
]

# Data value regex → column type
_DATA_PATTERNS: dict[_re.Pattern, str] = {
    _re.compile(r"^-?\d{1,3}(?:,\d{3})*(?:\.\d{2})$"): "amount",  # 1,234.56
    _re.compile(r"^-?\d+(?:\.\d+)?$"): "amount",  # 1234.56
    _re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2}$"): "date",  # 2024-01-15
    _re.compile(r"^\d{4}年\d{1,2}月\d{1,2}日$"): "date",  # 2024年01月15日
    _re.compile(r"^\d{15,19}$"): "account",  # 16-19 digit account
    _re.compile(r"^\d{17}[\dXx]$"): "account",  # 18 digit ID
}

_LABEL_SUFFIX_TO_TYPE: dict[str, str] = {
    "金额": "amount",
    "价款": "amount",
    "币种": "amount",
    "日期": "date",
    "期限": "date",
    "账号": "account",
    "卡号": "account",
    "户名": "name",
    "名称": "name",
    "摘要": "text",
    "用途": "text",
    "备注": "text",
}

_TYPE_FORMATS: dict[str, list[str]] = {
    "amount": ["#,##0.00", "#,##0", "0.00"],
    "date": ["YYYY-MM-DD", "YYYY/MM/DD", "YYYY年MM月DD日"],
    "account": ["16-19 digit numeric", "alphanumeric code"],
    "name": ["unicode text", "CJK characters"],
    "code": ["alphanumeric code"],
    "text": ["free text"],
}


@dataclass
class ColumnContext:
    """Context information for one column in a table or structure.

    Carries the inferred type, supporting evidence, and format expectations
    so that :class:`ContextAwarePostProcessor` can apply the correct
    correction chain.
    """

    column_index: int = 0
    header_text: str | None = None
    inferred_type: str = "unknown"  # "date", "amount", "name", "account", "code", "text", "unknown"
    confidence: float = 0.0
    column_bands: list[dict] = field(default_factory=list)
    supported_formats: list[str] = field(default_factory=list)

    @classmethod
    def unknown(cls, column_index: int = 0) -> ColumnContext:
        """Default context for a column with no type information."""
        return cls(column_index=column_index, inferred_type="unknown", confidence=0.0)


def infer_column_type(
    header_text: str | None = None,
    sample_values: list[str] | None = None,
    label_suffixes: list[str] | None = None,
    column_index: int = 0,
) -> ColumnContext:
    """Infer column type from header text, sample data values, and label suffixes.

    Priority (highest first):
        1. Label suffix match (e.g. ``金额`` → amount)
        2. Header pattern match (e.g. ``到期日期`` → date)
        3. Data value pattern match (e.g. ``1,234.56`` → amount)
        4. Fallback → unknown

    Args:
        header_text: Column header cell text (if available).
        sample_values: Up to 20 sample data values from the column body.
        label_suffixes: Suffix tokens extracted from the column band label.
        column_index: Column index for the returned context.

    Returns:
        :class:`ColumnContext` with inferred type and confidence.
    """
    # Priority 1: Label suffix match (most reliable)
    if label_suffixes:
        for suffix in label_suffixes:
            matched_type = _LABEL_SUFFIX_TO_TYPE.get(suffix)
            if matched_type:
                return ColumnContext(
                    column_index=column_index,
                    header_text=header_text,
                    inferred_type=matched_type,
                    confidence=0.9,
                    column_bands=[],
                    supported_formats=list(_TYPE_FORMATS.get(matched_type, [])),
                )

    # Priority 2: Header pattern match
    if header_text:
        for pattern, col_type in _HEADER_PATTERNS:
            if pattern.search(header_text):
                return ColumnContext(
                    column_index=column_index,
                    header_text=header_text,
                    inferred_type=col_type,
                    confidence=0.8,
                    column_bands=[],
                    supported_formats=list(_TYPE_FORMATS.get(col_type, [])),
                )

    # Priority 3: Data value pattern match
    if sample_values:
        type_votes: dict[str, int] = {}
        for value in sample_values[:20]:
            for pattern, col_type in _DATA_PATTERNS.items():
                if pattern.match(value):
                    type_votes[col_type] = type_votes.get(col_type, 0) + 1
                    break
        if type_votes:
            best_type = max(type_votes, key=type_votes.get)
            best_count = type_votes[best_type]
            if best_count >= max(1, len(sample_values[:20]) * 0.6):
                return ColumnContext(
                    column_index=column_index,
                    header_text=header_text,
                    inferred_type=best_type,
                    confidence=0.7,
                    column_bands=[],
                    supported_formats=list(_TYPE_FORMATS.get(best_type, [])),
                )

    # Priority 4: Fallback
    return ColumnContext(
        column_index=column_index,
        header_text=header_text,
        inferred_type="unknown",
        confidence=0.0,
        column_bands=[],
        supported_formats=[],
    )


class ContextAwarePostProcessor:
    """Column-aware OCR post-processing.

    Uses GCR-derived column context to select a column-specific correction
    chain for each cell.  Falls back to the generic 7-layer pipeline when
    no column context is available.

    The correction chains are defined declaratively in
    :data:`_COLUMN_CORRECTION_CHAINS` and resolved at init time from the
    module-level correction functions in ``ocr_postprocess.py``.
    """

    def __init__(self) -> None:
        # Resolve chain function names to callables at init time
        import docmirror.ocr.ocr_postprocess as _mod

        self._chains: dict[str, list[Callable[[str], str]]] = {}
        for col_type, func_names in _COLUMN_CORRECTION_CHAINS.items():
            resolved: list[Callable[[str], str]] = []
            for name in func_names:
                fn = getattr(_mod, name, None)
                if fn is not None and callable(fn):
                    resolved.append(fn)
                else:
                    logger.debug("[CAPP] Correction function %s not found for type=%s", name, col_type)
            if not resolved:
                # Fallback: use postprocess_ocr_text as last resort
                resolved.append(postprocess_ocr_text)
            self._chains[col_type] = resolved

    def process_cell(
        self,
        text: str,
        column_context: ColumnContext | None = None,
    ) -> str:
        """Apply column-appropriate correction to one cell.

        Args:
            text: Raw OCR text for this cell.
            column_context: Column type context.  ``None`` or
                ``inferred_type="unknown"`` triggers the full 7-layer pipeline.

        Returns:
            Corrected text.
        """
        if not text or not text.strip():
            return text

        if column_context is None or column_context.inferred_type == "unknown":
            # No context → full generic pipeline
            return postprocess_ocr_text(text)

        # Select column-specific correction chain
        chain = self._chains.get(column_context.inferred_type)
        if not chain:
            return postprocess_ocr_text(text)

        result = text
        for correction_fn in chain:
            try:
                result = correction_fn(result)
            except Exception as exc:
                logger.debug("[CAPP] Correction %s failed: %s", correction_fn.__name__, exc)
        return result

    def process_table(
        self,
        table: list[list[str]],
        col_contexts: list[ColumnContext | None] | None = None,
    ) -> list[list[str]]:
        """Apply column-appropriate correction to every cell in a table.

        Args:
            table: 2-D list of cell strings.
            col_contexts: Per-column contexts.  ``None`` or shorter than the
                number of columns causes the full pipeline to be applied
                to the un-contexted columns.

        Returns:
            Corrected table.
        """
        corrected: list[list[str]] = []
        for row_idx, row in enumerate(table):
            corrected_row: list[str] = []
            for col_idx, cell in enumerate(row):
                ctx = col_contexts[col_idx] if col_contexts and col_idx < len(col_contexts) else None
                corrected_row.append(self.process_cell(cell, ctx))
            corrected.append(corrected_row)
        return corrected


def enrich_col_bands_with_context(
    col_bands: list[dict[str, Any]],
    header_texts: list[str | None],
    sample_values: list[list[str]],
) -> list[dict[str, Any]]:
    """Attach column type context to each column band.

    Intended for use with ``field_grid/bands.py`` output.  Each band dict
    gets a ``"column_context"`` key with the serialised
    :class:`ColumnContext`.

    Args:
        col_bands: List of column band dicts from GCR or field_grid.
        header_texts: Per-column header text (or ``None``).
        sample_values: Per-column sample data values.

    Returns:
        Enriched column bands (modified in place and returned).
    """
    for idx, band in enumerate(col_bands):
        header = header_texts[idx] if idx < len(header_texts) else None
        samples = sample_values[idx] if idx < len(sample_values) else []
        context = infer_column_type(
            header_text=header,
            sample_values=samples,
            column_index=idx,
        )
        band["column_context"] = {
            "column_index": context.column_index,
            "header_text": context.header_text,
            "inferred_type": context.inferred_type,
            "confidence": context.confidence,
            "supported_formats": list(context.supported_formats),
        }
    return col_bands


def postprocess_table_context_aware(
    table: list[list[str]],
    col_contexts: list[ColumnContext | None] | None = None,
) -> list[list[str]]:
    """Convenience wrapper: build a ``ContextAwarePostProcessor`` and call
    ``process_table()`` in one step.

    Args:
        table: 2-D list of cell strings.
        col_contexts: Per-column contexts (``None`` → full pipeline).

    Returns:
        Corrected table.
    """
    processor = ContextAwarePostProcessor()
    return processor.process_table(table, col_contexts)
