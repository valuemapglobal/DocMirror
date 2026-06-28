# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Table pipeline domain stage — profile-specific hook dispatch.

Purpose: Resolves and runs registered domain hooks (ledger, generic) after
structure normalization.

Main components: ``run_stages``, ``resolve_hook_names``.

Upstream: ``table.pipeline`` stage chain.

Downstream: ``table.pipeline.hooks.*``, ``table.ledger_postprocess``.
"""

from __future__ import annotations

from typing import Any

from . import stage_header, stage_structure


def resolve_hook_names(profile: Any | None) -> list[str]:
    """Resolve TNP domain hooks from profile (YAML ``table_normalize_hooks`` or defaults)."""
    if profile is not None:
        hooks = getattr(profile, "table_normalize_hooks", None)
        if hooks:
            resolved = list(hooks)
            # Borderless ledger must not run generic first — junk/header filtering on
            # continuation pages drops ~1 row/page (design-12 P6-bench RCA).
            if getattr(profile, "is_borderless_ledger", lambda: False)():
                resolved = [h for h in resolved if h != "generic"]
                if not resolved:
                    resolved = ["ledger_borderless"]
            return resolved
        if getattr(profile, "is_borderless_ledger", lambda: False)():
            return ["ledger_borderless"]
    return ["generic"]


def run_stages(
    ctx: Any,
    rows: list[list[str]],
) -> tuple[list[list[str]], dict[str, str]]:
    """Run header → structure stages (parity with ``post_process_table``)."""
    confirmed = getattr(ctx, "confirmed_header", None)
    rows, preamble_kv, resolved_header = stage_header.run_header_stage(
        rows,
        confirmed_header=confirmed,
    )
    if not rows:
        return [], preamble_kv
    if resolved_header is None:
        return rows, preamble_kv

    header = rows[0]
    data_rows = list(rows[1:])
    data_rows = stage_structure.filter_junk_rows(header, data_rows, preamble_kv)
    header, data_rows = stage_structure.apply_structure_fixes(header, data_rows)
    rows = stage_structure.clean_data_rows(header, data_rows)
    return rows, preamble_kv
