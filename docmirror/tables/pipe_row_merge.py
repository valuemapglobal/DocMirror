# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Shared pipe-delimited table row merge utilities.

Merges continuation rows where the sequence-number column is empty but other
columns carry overflow text (common in mainframe / bank ASCII pipe ledgers).

Pipeline role: used by Mirror ``pipe_strategy`` and Plugin ``pipe_text_table_builder``.

Key exports: ``merge_pipe_continuation_rows``.
"""

from __future__ import annotations


def merge_pipe_continuation_rows(table: list[list[str]]) -> list[list[str]]:
    """Merge continuation rows in a pipe-delimited table.

    Rule: if the first column (sequence number) is empty, the row is treated
    as a continuation of the previous row and its content is appended.
    """
    if not table or len(table) < 2:
        return table

    merged: list[list[str]] = [list(table[0])]
    for row in table[1:]:
        first_cell = row[0].strip() if row else ""
        has_content = any(c.strip() for c in row[1:])
        if not first_cell and has_content and merged:
            prev = merged[-1]
            for i in range(len(row)):
                if i < len(prev):
                    cell_text = row[i].strip()
                    if cell_text:
                        if prev[i].strip():
                            prev[i] = prev[i].strip() + cell_text
                        else:
                            prev[i] = cell_text
                elif cell_text := row[i].strip():
                    prev.append(cell_text)
        else:
            merged.append(list(row))

    return merged
