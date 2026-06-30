# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.tables.pipeline import TableNormalizeContext, normalize_table, resolve_hook_names


def test_tnp_generic_hook():
    rows = [["日期", "金额"], ["2024-01-01", "100.00"]]
    ctx = TableNormalizeContext(rows=rows, profile=None)
    assert resolve_hook_names(None) == ["generic"]
    out, kv = normalize_table(ctx)
    assert len(out) >= 2
    assert isinstance(kv, dict)


def test_tnp_ledger_profile_adds_hook():
    class _P:
        def is_borderless_ledger(self):
            return True

    assert resolve_hook_names(_P()) == ["ledger_borderless"]


def test_tnp_ledger_profile_strips_generic_hook():
    """YAML misconfig must not run generic before ledger (row preservation)."""

    class _P:
        table_normalize_hooks = ["generic", "ledger_borderless"]

        def is_borderless_ledger(self):
            return True

    assert resolve_hook_names(_P()) == ["ledger_borderless"]
