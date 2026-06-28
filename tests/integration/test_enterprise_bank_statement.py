# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for bank statement enterprise/finance editions."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.plugins._runtime.runner import run_plugin_extract_sync
from tests.contract.test_edition_schema_conformance import check_enterprise, check_finance

pytest.importorskip("docmirror_enterprise")
pytest.importorskip("docmirror_finance")

YINZUO = Path("tests/fixtures/bank_statement/重庆恒腾科技有限公司_银行流水_银座银行_20251229.pdf")


@pytest.mark.integration
@pytest.mark.skipif(not YINZUO.is_file(), reason="missing yinzuo fixture")
def test_enterprise_bank_yinzuo_conformance():
    mirror = asyncio.run(
        perceive_document(YINZUO, PerceiveOptions(enhance_mode="standard"))
    ).mirror

    with patch("docmirror.plugins.runner._is_edition_plugin_licensed", return_value=True):
        out = run_plugin_extract_sync(
            mirror,
            edition="enterprise",
            full_text=mirror.full_text,
            file_path=str(YINZUO),
        )

    assert out is not None
    errors = check_enterprise(out, str(YINZUO))
    assert not errors, errors
    assert out["quality"]["overall_score"] >= 0.9
    assert len(out["normalization"]["standard_records"]) == 6

    balance_rule = next(r for r in out["validation"]["rules"] if r["rule_code"] == "BALANCE_CHAIN_CHECK")
    assert balance_rule["status"] == "passed"


@pytest.mark.integration
@pytest.mark.skipif(not YINZUO.is_file(), reason="missing yinzuo fixture")
def test_finance_bank_yinzuo_conformance():
    mirror = asyncio.run(
        perceive_document(YINZUO, PerceiveOptions(enhance_mode="standard"))
    ).mirror

    with patch("docmirror.plugins.runner._is_edition_plugin_licensed", return_value=True):
        out = run_plugin_extract_sync(
            mirror,
            edition="finance",
            full_text=mirror.full_text,
            file_path=str(YINZUO),
        )

    assert out is not None
    errors = check_finance(out, str(YINZUO))
    assert not errors, errors
    assert out["schema_version"] == "3.0"
    assert out["quality"]["overall_score"] >= 0.9
