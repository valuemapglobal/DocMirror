# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Vocabulary-guided column boundary adjustment."""

from __future__ import annotations

import logging

from docmirror.core.table.pipeline.vocab_match import _find_vocab_words_in_string

logger = logging.getLogger(__name__)


def _adjust_boundaries_by_vocab(
    col_boundaries: list[float],
    header_chars: list[dict],
) -> list[float]:
    """Shift column boundaries that fall inside known header words."""
    text_chars = [c for c in header_chars if c["text"].strip()]
    if not text_chars:
        return col_boundaries

    full_text = "".join(c["text"] for c in text_chars)
    found = _find_vocab_words_in_string(full_text)
    if not found:
        return col_boundaries

    adjusted = list(col_boundaries)
    modified = False

    for word, start_idx, end_idx in found:
        if end_idx > len(text_chars):
            continue
        word_x0 = text_chars[start_idx]["x0"]
        word_x1 = text_chars[end_idx - 1]["x1"]

        for bi in range(1, len(adjusted) - 1):
            bx = adjusted[bi]
            if word_x0 + 1 < bx < word_x1 - 1:
                new_bx = word_x1 + 0.5
                logger.debug(f"vocab boundary fix: {bx:.1f}\u2192{new_bx:.1f} to preserve '{word}'")
                adjusted[bi] = new_bx
                modified = True
                break

    if modified:
        adjusted.sort()

    return adjusted
