# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SSO extended page sampling helpers."""

from __future__ import annotations

from docmirror.layout.structure_signals import build_sso_sample_text, sso_sample_page_indices
from docmirror.plugins._runtime.community import normalize_premium_document_type


class _FakePage:
    def __init__(self, text: str):
        self._text = text

    def get_text(self) -> str:
        return self._text


class _FakeDoc:
    def __init__(self, pages: list[str]):
        self._pages = [_FakePage(t) for t in pages]

    def __len__(self) -> int:
        return len(self._pages)

    def __getitem__(self, idx: int) -> _FakePage:
        return self._pages[idx]


def test_sso_sample_page_indices_short_doc():
    assert sso_sample_page_indices(5) == [0, 1, 2, 3, 4]


def test_sso_sample_page_indices_long_doc():
    assert sso_sample_page_indices(20) == list(range(10)) + [18, 19]


def test_build_sso_sample_text_concatenates_sample_pages():
    doc = _FakeDoc([f"p{i}" for i in range(12)])
    text = build_sso_sample_text(doc)
    assert "p0" in text and "p9" in text and "p10" in text and "p11" in text
    assert "p5" in text


def test_normalize_premium_document_type_m9():
    assert normalize_premium_document_type("bank_reconciliation") == "bank_statement"
    assert normalize_premium_document_type("credit_report_enterprise") == "credit_report"
    assert normalize_premium_document_type("wechat_payment") == "wechat_payment"
