# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Enterprise PEC integration — runs when docmirror_enterprise is on PYTHONPATH."""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest

from docmirror.models.entities.parse_result import DocumentEntities, PageContent, ParseResult, ResultStatus
from docmirror.models.entities.parse_result import TextBlock
from docmirror.plugins.post_extract.hooks.credit_sections import CreditReportSectionsHook
from docmirror.plugins.runner import run_plugin_extract_sync

pytest.importorskip("docmirror_enterprise")

BANK_FIXTURE = Path("tests/fixtures/bank_statement/银行流水_中国建设银行_20231226.pdf")


def test_enterprise_bank_statement_extract_smoke():
    if not BANK_FIXTURE.is_file():
        pytest.skip(f"missing fixture {BANK_FIXTURE}")

    pr = ParseResult(status=ResultStatus.SUCCESS)
    pr.entities = DocumentEntities(document_type="bank_statement")

    out = run_plugin_extract_sync(pr, edition="enterprise")
    assert out is not None
    assert out.get("edition") == "enterprise"


def test_enterprise_package_importable():
    assert importlib.import_module("docmirror_enterprise") is not None


def test_credit_report_section_splitter_importable():
    mod = importlib.import_module(
        "docmirror_enterprise.plugins.credit_report.extractors.section_splitter"
    )
    assert hasattr(mod, "SectionSplitter")


def test_credit_report_sections_hook_attaches_sections():
    sample_text = (
        "个人信用报告\n"
        "报告编号：202601010001\n"
        "一、个人基本信息\n"
        "姓名：张三\n"
        "二、信息概要\n"
        "账户数：2\n"
    )
    page = PageContent(page_number=1, texts=[TextBlock(content=sample_text)])
    pr = ParseResult(status=ResultStatus.SUCCESS, pages=[page])
    pr.entities = DocumentEntities(document_type="credit_report")

    with patch.object(type(pr), "full_text", new_callable=PropertyMock, return_value=sample_text):
        hook = CreditReportSectionsHook()
        hook.apply(
            pr,
            extracted={"edition": "enterprise"},
            edition="enterprise",
            document_type="credit_report",
            plugin=None,
        )

    assert len(pr.sections) >= 1


def test_bank_table_rebuild_hook_with_transactions():
    from docmirror.plugins.post_extract.hooks.mirror_table_rebuild import MirrorTableRebuildHook
    from docmirror.models.entities.parse_result import TableBlock, TableRow, CellValue, RowType

    page = PageContent(
        page_number=1,
        tables=[
            TableBlock(
                headers=["列1"],
                rows=[TableRow(cells=[CellValue(text="x")], row_type=RowType.DATA)],
            )
        ],
    )
    pr = ParseResult(status=ResultStatus.SUCCESS, pages=[page])
    pr.entities = DocumentEntities(document_type="bank_statement")

    extracted = {
        "structured_data": {
            "transactions": [
                {
                    "date": "2024-01-01",
                    "description": "工资",
                    "amount": 1000.0,
                    "type": "credit",
                    "balance": "1000.00",
                }
            ]
        }
    }
    hook = MirrorTableRebuildHook()
    hook.apply(
        pr,
        extracted=extracted,
        edition="enterprise",
        document_type="bank_statement",
        plugin=None,
    )
    assert pr.total_tables >= 2 or any(t.table_id == "bank_transactions_rebuilt" for t in pr.all_tables())
