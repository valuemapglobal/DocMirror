# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration test: bank statement community plugin on 银座银行 fixture."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from docmirror.core.entry.factory import PerceiveOptions, perceive_document
from docmirror.plugins.runner import run_plugin_extract_sync

YINZUO_FIXTURE = Path("tests/fixtures/bank_statement/重庆恒腾科技有限公司_银行流水_银座银行_20251229.pdf")


@pytest.mark.integration
@pytest.mark.skipif(not YINZUO_FIXTURE.is_file(), reason="yinzuo fixture missing")
def test_yinzuo_bank_statement_community_extract():
    mirror = asyncio.run(
        perceive_document(YINZUO_FIXTURE, PerceiveOptions(enhance_mode="standard"))
    ).mirror

    out = run_plugin_extract_sync(
        mirror,
        edition="community",
        full_text=mirror.full_text,
        file_path=str(YINZUO_FIXTURE),
    )
    assert out is not None
    records = out["data"]["records"]
    assert len(records) == 6

    first = records[0]["normalized"]
    assert first["date"] == "2025-09-21"
    assert first["amount"] == pytest.approx(0.04)
    assert first["balance"] == pytest.approx(306.09)
    assert first["summary"] == "结息"

    expense_row = next(r for r in records if r["normalized"].get("amount") == 3765000.00)
    norm = expense_row["normalized"]
    assert norm["date"] == "2025-10-27"
    assert norm["counter_account"].startswith("010415600120")

    summary = out["data"]["summary"]
    assert summary["total_rows"] == 6
    assert summary["total_expense"] > 0
