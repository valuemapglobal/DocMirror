# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Unified header cell normalizer — single cached normalization entry for all plugins.

Replaces scattered regex/NFKC/whitespace logic with a single lru_cache-backed
function. Both ``header_resolve.normalize_header_cell`` and ``ColumnMatcher._clean``
can delegate to this shared surface.

Pipeline role: called by bank-statement header_resolve (NFKC path) and optionally
by ColumnMatcher (non-NFKC path). Caching is global across all callers.

Key exports: ``normalize_header``.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

_WS_RE = re.compile(r"[\s\n\r\t\u3000]")


@lru_cache(maxsize=1024)
def normalize_header(text: str, *, nfkc: bool = True) -> str:
    """Normalize a raw OCR header to a canonical, comparable form.

    Args:
        text: Raw header string (cell text from table extraction).
        nfkc: Enable NFKC normalization (default True for bank_statement;
              set False for ColumnMatcher compatibility).

    Returns:
        Normalized string suitable for equality comparison and dict lookup.
        Empty string returned unchanged.
    """
    s = str(text or "").strip()
    if not s:
        return s
    if nfkc:
        s = unicodedata.normalize("NFKC", s)
    return _WS_RE.sub("", s).replace("\u00a0", "")
