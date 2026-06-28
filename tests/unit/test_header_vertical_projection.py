# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Header vertical projection column grouping."""

from __future__ import annotations

from docmirror.structure.tables.header_reconstruction import _group_chars_by_column_gaps


def test_group_chars_by_column_gaps():
    chars = [
        {"text": "A", "x0": 10},
        {"text": "B", "x0": 12},
        {"text": "C", "x0": 50},
        {"text": "D", "x0": 52},
    ]
    grouped = _group_chars_by_column_gaps(chars, [30.0])
    assert grouped == ["AB", "CD"]
