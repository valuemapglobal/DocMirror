# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Institution Authority Stack (IAS) tests."""

from __future__ import annotations

from docmirror.plugins.bank_statement.context import StyleContext
from docmirror.plugins.bank_statement.institution_authority import (
    extract_identity_from_header,
    resolve_institution_hint,
)


def test_organization_over_body_keyword():
    header = "开户行     中国银行南京浦东路支行"
    body = "对方户名 李正华/中国建设银行股份有限公司"
    text = header + "\n|序号|记账日|" + body
    ctx = StyleContext(
        tables=[],
        full_text=text,
        institution="中国银行",
        page_count=1,
    )
    hint, authority = resolve_institution_hint(ctx, {"中国建设银行": ["建设银行"]})
    assert hint == "中国银行"
    assert authority == "entities.organization"


def test_header_only_ccb_not_in_transactions():
    header = "开户行     中国银行南京浦东路支行\n账户名称  测试公司"
    body = "交易明细\n| 1 |220401|...|中国建设银行股份有限公司|"
    text = header + "\n|序号|记账日|借方发生额|贷方发生额|\n" + body
    ctx = StyleContext(
        tables=[],
        full_text=text,
        institution=None,
        page_count=1,
    )
    hint, _ = resolve_institution_hint(
        ctx,
        {"中国建设银行": ["建设银行"], "中国银行": ["中国银行"]},
    )
    assert hint is not None
    assert "中国银行" in hint


def test_filename_bank_token_priority_over_body_keyword():
    from docmirror.plugins.bank_statement.context import StyleContext
    from docmirror.plugins.bank_statement.institution_authority import resolve_institution_hint

    text = "对方户名 李正华/中国建设银行股份有限公司\n|序号|记账日|"
    ctx = StyleContext(
        tables=[],
        full_text=text,
        institution=None,
        page_count=1,
        parse_result=type("PR", (), {"file_path": "/tmp/中国银行-南京创沃电气设备有限公司_1.pdf"})(),
    )
    hint, authority = resolve_institution_hint(ctx, {"中国建设银行": ["建设银行"]})
    assert hint is not None
    assert "中国银行" in hint
    assert authority == "filename.token"


def test_extract_identity_from_header():
    text = (
        "账号     544362180589         账户名称  南京创沃电气设备有限公司"
        "                                        开户行     中国银行南京浦东路支行"
        "起始日期20220401                              截止日期 20220430"
        "\n|序号|记账日|"
    )
    identity = extract_identity_from_header(text)
    assert identity["account_holder"] == "南京创沃电气设备有限公司"
    assert identity["account_number"] == "544362180589"
    assert "2022-04-01" in identity["query_period"]
