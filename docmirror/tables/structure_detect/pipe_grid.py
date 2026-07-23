# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Pipe grid detection — SDU SSOT for ASCII pipe-delimited ledgers.

Document-agnostic: detects split debit/credit pipe headers and primary rows.
Used by Mirror pipe_strategy, SSO H_pipe_grid, and Plugin LTRO wrappers.

Key exports: ``PipeGridSignal``, ``detect_pipe_grid_in_text``, ``detect_pipe_grid_page``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from docmirror.layout.profile.registry import load_table_semantics

_PIPE_RULES = load_table_semantics().get("pipe_grid") or {}
_RAW_HEADER_PATTERNS = tuple(str(pattern) for pattern in _PIPE_RULES.get("header_patterns", ()))
_COMPILED_HEADER_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in _RAW_HEADER_PATTERNS)
_NEVER_MATCH = re.compile(r"(?!x)x")
_PIPE_HEADER_ZH = _COMPILED_HEADER_PATTERNS[0] if _COMPILED_HEADER_PATTERNS else _NEVER_MATCH
_PIPE_HEADER_EN = _COMPILED_HEADER_PATTERNS[1] if len(_COMPILED_HEADER_PATTERNS) > 1 else _NEVER_MATCH
_SPLIT_AMOUNT_MARKERS = tuple(str(value) for value in _PIPE_RULES.get("split_amount_markers", ()))
_PRIMARY_ROW_RE = re.compile(r"^\|\s*\d+\s*\|")
_HLINE_RE = re.compile(r"^[\s─━\-|]+$")
_FOOTER_MARKERS = tuple(str(value) for value in _PIPE_RULES.get("footer_markers", ()))
_HEADER_REPEAT_RE = _PIPE_HEADER_ZH
# Markdown tables: | col | col | without ledger sequence + split amount headers
_MARKDOWN_PIPE_ONLY = re.compile(r"^\|\s*[^|]+\|\s*[^|]+\|")


@dataclass(frozen=True)
class PipeGridSignal:
    header_detected: bool
    split_debit_credit: bool
    expected_primary_rows: int
    confidence: float


def split_pipe_row(line: str) -> list[str]:
    """Split a pipe-delimited line into trimmed cell values."""
    parts = [p.strip() for p in line.split("|")]
    if line.strip().startswith("|") and parts and parts[0] == "":
        parts = parts[1:]
    if line.strip().endswith("|") and parts and parts[-1] == "":
        parts = parts[:-1]
    return parts


def _line_has_split_amount_headers(line: str) -> bool:
    return any(m in line for m in _SPLIT_AMOUNT_MARKERS)


def detect_pipe_header_in_text(text: str) -> bool:
    """True when text looks like a pipe ledger with split debit/credit columns."""
    return detect_pipe_grid_in_text(text).header_detected


def _is_header_row(line: str) -> bool:
    return bool(_HEADER_REPEAT_RE.search(line)) and _line_has_split_amount_headers(line)


def _is_data_row(line: str) -> bool:
    stripped = line.strip()
    if not stripped or not stripped.startswith("|"):
        return False
    if _HLINE_RE.match(stripped):
        return False
    if any(m in stripped for m in _FOOTER_MARKERS):
        return False
    return bool(_PRIMARY_ROW_RE.match(stripped))


def count_primary_pipe_rows(text: str) -> int:
    """Count primary pipe rows (sequence number in first column)."""
    if not text:
        return 0
    return sum(1 for line in text.splitlines() if _is_data_row(line.strip()))


def _markdown_pipe_negative(text: str) -> bool:
    """True when pipes look like Markdown tables, not bank ledgers."""
    if not text or "|" not in text:
        return False
    has_ledger_header = False
    markdown_rows = 0
    for line in text.splitlines()[:40]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if _is_header_row(stripped) or _PIPE_HEADER_ZH.search(stripped):
            has_ledger_header = True
        if _MARKDOWN_PIPE_ONLY.match(stripped) and not _is_data_row(stripped):
            if "---" in stripped or ":-:" in stripped:
                return True
            markdown_rows += 1
    return not has_ledger_header and markdown_rows >= 2


def detect_pipe_grid_in_text(text: str) -> PipeGridSignal:
    """Score pipe grid presence in plain text (Mirror full_text or page text)."""
    if not text or "|" not in text:
        return PipeGridSignal(False, False, 0, 0.0)

    if _markdown_pipe_negative(text):
        return PipeGridSignal(False, False, 0, 0.05)

    header_detected = False
    split_debit_credit = False
    for i, line in enumerate(text.splitlines()):
        if not (_PIPE_HEADER_ZH.search(line) or _PIPE_HEADER_EN.search(line)):
            continue
        window = "\n".join(text.splitlines()[i : i + 3])
        if _line_has_split_amount_headers(window):
            header_detected = True
            split_debit_credit = True
            break

    if not header_detected:
        return PipeGridSignal(False, False, 0, 0.0)

    primary_rows = count_primary_pipe_rows(text)
    confidence = 0.5
    if split_debit_credit:
        confidence += 0.25
    if primary_rows >= 3:
        confidence += min(0.25, primary_rows / 200.0)
    confidence = min(1.0, confidence)

    return PipeGridSignal(
        header_detected=True,
        split_debit_credit=split_debit_credit,
        expected_primary_rows=primary_rows,
        confidence=round(confidence, 4),
    )


def page_has_no_drawing_primitives(page_plum) -> bool:
    """G1 gate: pipe_delimited only when PDF has no vector lines/rects."""
    pdf_lines = page_plum.lines or []
    pdf_rects = page_plum.rects or []
    return not pdf_lines and not pdf_rects


def detect_pipe_grid_page(page_plum) -> PipeGridSignal | None:
    """Detect pipe grid on a pdfplumber page; None when G1 fails or no signal."""
    if not page_has_no_drawing_primitives(page_plum):
        return None
    try:
        text = page_plum.extract_text() or ""
    except Exception:
        text = ""
    signal = detect_pipe_grid_in_text(text)
    if signal.header_detected:
        return signal
    return None
