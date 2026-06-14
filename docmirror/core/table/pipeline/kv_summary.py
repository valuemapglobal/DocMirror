# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Summary-zone KV extraction (page assemble, not TNP normalize)."""

from __future__ import annotations

import re
from collections import defaultdict

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
    for segment in re.split(r"\s{2,}|\n", full):
        segment = segment.strip()
        if not segment:
            continue
        _parse_kv_segment(segment, out)


# Common KV key pattern (short CJK word + colon)
_KV_EMBEDDED_RE = re.compile(
    r"([\u4e00-\u9fff]{2,6})"  # 2\u20136 CJK characters (key)
    r"[\uff1a:]"  # Colon separator
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
    "\u5e01\u79cd",
    "\u6237\u540d",
    "\u8d26\u53f7",
    "\u5361\u53f7",
    "\u8d26\u6237",
    "\u7c7b\u578b",
    "\u65e5\u671f",
    "\u59d3\u540d",
    "\u7f16\u53f7",
    "\u72b6\u6001",
    "\u5907\u6ce8",
    "\u6458\u8981",
    "\u91d1\u989d",
    "\u4f59\u989d",
    "\u884c\u540d",
    "\u8d77\u6b62\u65e5\u671f",
    "\u8d77\u59cb\u65e5\u671f",
    "\u622a\u6b62\u65e5\u671f",
    "\u7ec8\u6b62\u65e5\u671f",
    "\u6253\u5370\u65e5\u671f",
    "\u603b\u7b14\u6570",
    "\u603b\u91d1\u989d",
    "\u9875\u7801",
    "\u673a\u6784",
]


def _find_embedded_kv_by_keywords(v: str) -> int | None:
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


def _find_embedded_kv_by_colon_scan(v: str) -> int | None:
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
            while scan >= 0 and "\u4e00" <= v[scan] <= "\u9fff":
                cjk_before += 1
                scan -= 1
            # 2\u20134 CJK chars + preceding non-CJK content \u2192 possibly an embedded key
            if 2 <= cjk_before <= 4 and scan >= 0:
                key_start = idx - cjk_before
                if best_pos is None or key_start > best_pos:
                    best_pos = key_start
            pos = idx + 1
    return best_pos
