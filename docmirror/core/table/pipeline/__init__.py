# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Table normalization pipeline — staged table cleanup orchestrator.

Purpose: Registers hooks and runs preamble → header → structure → domain
stages via ``normalize_table`` and ``TableNormalizeContext``.

Main components: ``normalize_table``, ``TableNormalizeContext``,
``register_tnp_hook``.

Upstream: ``table.postprocess``, ``extraction.table_postprocessor``.

Downstream: Composed table blocks, ``table.compose``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from collections.abc import Callable

from . import stage_domain, stage_header, stage_preamble, stage_structure
from docmirror.core.table.pipeline.hooks.generic import run_generic_hook
from docmirror.core.table.pipeline.hooks.ledger_borderless import run_ledger_borderless_hook


@dataclass(frozen=True)
class TableNormalizeContext:
    rows: list[list[str]]
    profile: Any | None = None
    page_idx: int = 0
    source_layer: str = ""
    confirmed_header: list[str] | None = None


TableNormalizeHook = Callable[[TableNormalizeContext, list[list[str]]], tuple[list[list[str]], dict[str, str]]]

TNP_HOOKS: dict[str, TableNormalizeHook] = {}


def register_tnp_hook(name: str, hook: TableNormalizeHook) -> None:
    TNP_HOOKS[name] = hook


def resolve_hook_names(profile: Any | None) -> list[str]:
    return stage_domain.resolve_hook_names(profile)


register_tnp_hook("generic", run_generic_hook)
register_tnp_hook("ledger_borderless", run_ledger_borderless_hook)


def normalize_table(ctx: TableNormalizeContext) -> tuple[list[list[str]], dict[str, str]]:
    """Run TNP domain hooks for ``ctx.rows``; returns (processed_rows, preamble_kv)."""
    rows = [list(r) for r in ctx.rows]
    preamble_kv: dict[str, str] = {}
    for hook_name in resolve_hook_names(ctx.profile):
        hook = TNP_HOOKS.get(hook_name, run_generic_hook)
        rows, kv = hook(ctx, rows)
        if kv:
            preamble_kv.update(kv)
    return rows, preamble_kv


__all__ = [
    "TableNormalizeContext",
    "TNP_HOOKS",
    "normalize_table",
    "register_tnp_hook",
    "resolve_hook_names",
    "stage_domain",
    "stage_header",
    "stage_preamble",
    "stage_structure",
]
