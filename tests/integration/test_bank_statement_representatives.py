# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Representative bank fixtures — BLO/CQF integration (issue.md clusters)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests/fixtures/bank_statement"

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _fixture(name: str) -> Path:
    path = FIXTURES / name
    if not path.is_file():
        pytest.skip(f"fixture missing: {name}")
    return path


@pytest.fixture(scope="module")
def bank_plugin():
    from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin

    return BankStatementCommunityPlugin()


@pytest.fixture(scope="module")
def perceive_fixture():
    import asyncio

    from docmirror.core.entry.factory import perceive_document

    async def _run(path: Path):
        return await perceive_document(path)

    def _sync(path: Path):
        return asyncio.run(_run(path))

    return _sync


def _extract(path: Path, perceive_fixture, bank_plugin):
    from docmirror.plugins.bank_statement.extract_pipeline import run_bank_statement_extract

    pr = perceive_fixture(path)
    text = pr.full_text or getattr(pr, "extractor_full_text", "") or ""
    return run_bank_statement_extract(pr, text, bank_plugin)


@pytest.mark.skipif(
    not os.environ.get("DOCMIRROR_RUN_BANK_REPRESENTATIVES"),
    reason="Set DOCMIRROR_RUN_BANK_REPRESENTATIVES=1 for full PDF representative tests",
)
def test_abc_multi_lt_exports_canonical_rows(perceive_fixture, bank_plugin):
    """BS-011: ABC 11-page multi logical table — BLO should export meaningful canonical rows."""
    result = _extract(_fixture("农行-上海宏立机械设备租赁有限公司_1.pdf"), perceive_fixture, bank_plugin)
    assert result.style_meta.canonical_extracted >= 50
    assert result.style_meta.canonical_ratio >= 0.35
    assert result.style_meta.extract_status != "degraded"


@pytest.mark.skipif(
    not os.environ.get("DOCMIRROR_RUN_BANK_REPRESENTATIVES"),
    reason="Set DOCMIRROR_RUN_BANK_REPRESENTATIVES=1",
)
def test_liming_guizhou_has_records(perceive_fixture, bank_plugin):
    """BS-014: 黎明贵州银行 — was 0 records; BLO fallback should yield rows."""
    result = _extract(_fixture("黎明_银行流水_贵州银行_20250530.pdf"), perceive_fixture, bank_plugin)
    assert len(result.records) >= 1
    assert result.style_meta.extract_status in ("degraded", "low_coverage")


@pytest.mark.skipif(
    not os.environ.get("DOCMIRROR_RUN_BANK_REPRESENTATIVES"),
    reason="Set DOCMIRROR_RUN_BANK_REPRESENTATIVES=1",
)
def test_taizhou_has_records(perceive_fixture, bank_plugin):
    """BS-014: 台州银行 — was 0 records."""
    result = _extract(_fixture("浙江天宏国际物流有限公司_银行流水_台州银行_20240329.pdf"), perceive_fixture, bank_plugin)
    assert len(result.records) >= 1


@pytest.mark.skipif(
    not os.environ.get("DOCMIRROR_RUN_BANK_REPRESENTATIVES"),
    reason="Set DOCMIRROR_RUN_BANK_REPRESENTATIVES=1",
)
def test_guangda_not_false_success(perceive_fixture, bank_plugin):
    """BS-013: 光大 525 rows all direction other — CQF must not report success."""
    result = _extract(
        _fixture("安徽康安设备吊装工程有限公司_银行流水_光大银行_20240902.pdf"),
        perceive_fixture,
        bank_plugin,
    )
    assert result.style_meta.extract_status in ("degraded", "low_coverage")
    assert result.style_meta.canonical_ratio < 0.5
