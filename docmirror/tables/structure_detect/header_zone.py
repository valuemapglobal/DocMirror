# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Header zone extraction — text region before tabular body (entity regex scope)."""

from __future__ import annotations

from typing import Any

from docmirror.tables.structure_detect.pipe_grid import (
    _HEADER_REPEAT_RE,
    _PIPE_HEADER_EN,
    _PIPE_HEADER_ZH,
)

_DEFAULT_MAX_CHARS = 2000


def _first_pipe_header_index(text: str) -> int | None:
    for i, line in enumerate(text.splitlines()):
        if _PIPE_HEADER_ZH.search(line) or _PIPE_HEADER_EN.search(line) or _HEADER_REPEAT_RE.search(line):
            return sum(len(ln) + 1 for ln in text.splitlines()[:i])
    return None


def _first_table_block_index(full_text: str, parse_result: Any) -> int | None:
    """Byte offset in full_text before first table header cell (§3.7)."""
    if not full_text or parse_result is None:
        return None
    for page in getattr(parse_result, "pages", []) or []:
        for table in getattr(page, "tables", []) or []:
            headers = getattr(table, "headers", None) or []
            for header in headers:
                needle = str(header or "").strip()
                if len(needle) >= 2 and needle in full_text:
                    return full_text.index(needle)
    return None


def extract_header_zone(
    full_text: str,
    *,
    max_chars: int = _DEFAULT_MAX_CHARS,
    parse_result: Any = None,
) -> str:
    """Return header region before pipe ledger, first table block, or max_chars."""
    if not full_text:
        return ""
    end = len(full_text)
    pipe_idx = _first_pipe_header_index(full_text)
    if pipe_idx is not None and pipe_idx > 0:
        end = min(end, pipe_idx)
    table_idx = _first_table_block_index(full_text, parse_result)
    if table_idx is not None and table_idx > 0:
        end = min(end, table_idx)
    return full_text[: min(end, max_chars)]
