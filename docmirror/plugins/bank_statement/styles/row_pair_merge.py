# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Multiline continuation row pairing for compact bank ledgers.

Detects time-only continuation rows and merges counterparty/summary fragments into
the pending transaction dict produced by compact merged parsing.

Pipeline role: helper for ``compact_merged`` style parser when ledger rows span
multiple physical table rows.

Key exports: ``PARSER_ID``, ``is_continuation_row``, ``merge_continuation_into_pending``,
``pair_ledger_rows``.
"""

from __future__ import annotations

import re

_TIME_RE = re.compile(r"^\d{1,2}:\d{2}:\d{2}$")
_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")

PARSER_ID = "row_pair_merge"


def is_continuation_row(first_cell: str) -> bool:
    return bool(_TIME_RE.match((first_cell or "").strip()))


def merge_continuation_into_pending(
    pending: dict[str, str],
    *,
    time_cell: str = "",
    counterparty_cell: str = "",
) -> None:
    if time_cell:
        pending["time_cell"] = time_cell.strip()
    if counterparty_cell:
        pending["counterparty_cell"] = (pending.get("counterparty_cell", "") + counterparty_cell).strip()


def pair_ledger_rows(
    table: list[list[str]],
    *,
    header_idx: int,
    col_ledger: int,
    col_cp: int,
    col_summary: int,
) -> list[dict[str, str]]:
    """Pair primary ledger rows with time/counterparty continuation rows."""
    transactions: list[dict[str, str]] = []
    pending: dict[str, str] | None = None

    for row in table[header_idx + 1 :]:
        cells = [str(c or "").strip() for c in row]
        while len(cells) <= max(col_ledger, col_cp, col_summary):
            cells.append("")

        first = cells[col_ledger]
        if not any(cells):
            continue
        if any(kw in first for kw in ("合计", "小计", "总计", "本页")):
            continue

        if _DATE_PREFIX_RE.match(first):
            if pending:
                transactions.append(pending)
            pending = {
                "ledger_cell": first,
                "counterparty_cell": cells[col_cp],
                "summary": cells[col_summary],
                "time_cell": "",
            }
        elif is_continuation_row(first) and pending:
            merge_continuation_into_pending(
                pending,
                time_cell=first,
                counterparty_cell=cells[col_cp],
            )
        elif pending and cells[col_cp] and not first:
            merge_continuation_into_pending(pending, counterparty_cell=cells[col_cp])

    if pending:
        transactions.append(pending)
    return transactions
