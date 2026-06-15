# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Vocab match — finds dictionary terms inside header strings.

Purpose: Locates vocabulary category words in header cell text to score and
align header rows during normalization.

Main components: ``find_vocab_words_in_string``.

Upstream: Header cell strings, ``utils.vocabulary``.

Downstream: ``table.pipeline.stage_header``, ``extract.char.vocab_boundary``.
"""

from __future__ import annotations

from docmirror.core.utils.vocabulary import _AC_ALL, _AC_BY_CATEGORY, _normalize_for_vocab


def find_vocab_words_in_string(
    s: str,
    categories: list[str] | None = None,
) -> list[tuple[str, int, int]]:
    """Find known header words in ``s`` via Aho-Corasick longest non-overlapping match."""
    s = _normalize_for_vocab(s)
    if categories and len(categories) == 1:
        ac = _AC_BY_CATEGORY.get(categories[0], _AC_ALL)
    else:
        ac = _AC_ALL
    return ac.search_longest_non_overlapping(s)


# Backward-compat alias
_find_vocab_words_in_string = find_vocab_words_in_string

__all__ = ["find_vocab_words_in_string", "_find_vocab_words_in_string"]
