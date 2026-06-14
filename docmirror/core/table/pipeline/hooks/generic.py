# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""TNP domain hook: generic table normalization."""

from __future__ import annotations

from typing import TYPE_CHECKING

from docmirror.core.table.pipeline.stage_domain import run_stages
from docmirror.core.table.postprocess import post_process_table

if TYPE_CHECKING:
    from docmirror.core.table.pipeline import TableNormalizeContext


def run_generic_hook(
    ctx: TableNormalizeContext,
    rows: list[list[str]],
) -> tuple[list[list[str]], dict[str, str]]:
    profile = getattr(ctx, "profile", None)
    if profile is not None and getattr(profile, "use_tnp_staged", False):
        return run_stages(ctx, rows)
    confirmed = getattr(ctx, "confirmed_header", None)
    out, kv = post_process_table(rows, confirmed_header=confirmed)
    if out is None:
        return [], kv
    return out, kv
