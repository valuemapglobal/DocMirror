# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""TNP domain hook: borderless ledger (precision-first, no row loss)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from docmirror.core.table.ledger_postprocess import post_process_ledger_table
from docmirror.core.table.postprocess import post_process_table

if TYPE_CHECKING:
    from docmirror.core.table.pipeline import TableNormalizeContext


def run_ledger_borderless_hook(
    ctx: TableNormalizeContext,
    rows: list[list[str]],
) -> tuple[list[list[str]], dict[str, str]]:
    if ctx.profile is None:
        return post_process_table(rows)
    out, kv = post_process_ledger_table(rows, ctx.profile)
    if out is None:
        return [], kv
    return out, kv
