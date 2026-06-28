# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Ledger borderless hook — borderless bank statement table finalize.

Purpose: Runs ledger-specific validation and column completion for borderless
statement profiles after generic structure stages.

Main components: ``run_ledger_borderless_hook``.

Upstream: ``stage_domain`` for borderless ledger profiles.

Downstream: ``table.ledger_postprocess``, ``table.wrap_recovery``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docmirror.tables.ledger_postprocess import post_process_ledger_table
from docmirror.tables.postprocess import post_process_table

if TYPE_CHECKING:
    from docmirror.tables.pipeline import TableNormalizeContext


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
