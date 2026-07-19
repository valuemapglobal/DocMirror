# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Focused tests for optional generic KV projections."""

from __future__ import annotations

from docmirror.models.entities.parse_result import ParseResult
from docmirror.plugins._base import kv_community_extract
from docmirror.plugins.credit_report.community_plugin import plugin


def test_credit_report_can_skip_expensive_generic_projections(monkeypatch) -> None:
    def _unexpected(_parse_result):
        raise AssertionError("generic projection must be skipped")

    monkeypatch.setattr(kv_community_extract, "collect_kv_fields_from_blocks", _unexpected)
    monkeypatch.setattr(kv_community_extract, "_collect_table_records", _unexpected)

    output = kv_community_extract.extract_kv_community_output(
        plugin,
        ParseResult(),
        identity_specs=plugin.identity_fields,
        full_text="姓名：张三 证件号码：11010519491231002X",
        include_block_kv=False,
        include_generic_records=False,
    )

    assert output["data"]["fields"]["subject_name"] == "张三"
    assert output["data"]["records"] == []
