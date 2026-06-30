# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Enterprise PEC integration — runs when docmirror_enterprise is on PYTHONPATH."""

from __future__ import annotations

import importlib
from unittest.mock import PropertyMock, patch

import pytest

from docmirror.models.entities.parse_result import DocumentEntities, PageContent, ParseResult, ResultStatus, TextBlock
from docmirror.plugins._runtime.post_extract.hooks.credit_sections import CreditReportSectionsHook
from docmirror.plugins._runtime.runner import run_plugin_extract_sync

pytest.importorskip("docmirror_enterprise")


def test_enterprise_bank_statement_extract_smoke():
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


def test_credit_report_sections_hook_attaches_sections_to_edition():
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
    extracted: dict = {"edition": "enterprise", "data": {}}

    with patch.object(type(pr), "full_text", new_callable=PropertyMock, return_value=sample_text):
        hook = CreditReportSectionsHook()
        hook.apply(
            pr,
            extracted=extracted,
            edition="enterprise",
            document_type="credit_report",
            plugin=None,
        )

    assert len(extracted.get("data", {}).get("sections") or []) >= 1
    assert not pr.sections


def test_bank_table_rebuild_hook_with_transactions():
    from docmirror.models.entities.parse_result import CellValue, RowType, TableBlock, TableRow
    from docmirror.plugins._runtime.post_extract.hooks.mirror_table_rebuild import MirrorTableRebuildHook

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
    enrichment = extracted.get("enrichment", {}).get("bank_table_rebuild") or {}
    assert enrichment.get("transaction_count") == 1
    assert enrichment.get("status") == "edition_only"
    assert pr.total_tables == 1
