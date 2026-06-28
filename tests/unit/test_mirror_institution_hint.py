# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mirror institution hint — header-first resolution."""

from __future__ import annotations

from docmirror.structure.scene.institution_hint import resolve_document_institution
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult


def test_header_bank_name_beats_body_keywords():
    text = (
        "开户行     中国银行南京浦东路支行\n"
        "账号 123456\n"
        "工行流水 误匹配关键词\n"
        "|序号|记账日|"
    )
    pr = ParseResult(full_text=text)
    inst, auth = resolve_document_institution(pr, text)
    assert inst == "中国银行南京浦东路支行"
    assert auth == "header.kv"
