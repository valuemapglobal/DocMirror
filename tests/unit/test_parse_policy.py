from __future__ import annotations

import pytest

from docmirror.input.entry.options import (
    ParsePolicy,
    normalize_parse_policy,
    parse_page_selection,
)


def test_page_selection_resolves_ranges_and_max_pages():
    selection = parse_page_selection("2-3,5-", max_pages=3)
    assert selection.resolve(8) == [1, 2, 4]
    assert selection.to_display() == "2-3,5- (max 3)"


def test_last_page_selection_resolves_from_document_end():
    selection = parse_page_selection("last:2")
    assert selection.resolve(10) == [8, 9]


def test_parse_policy_contains_fact_options_only():
    policy = normalize_parse_policy(mode="fast", doc_type_hint="bank_statement")
    assert policy.enhance_mode == "raw"
    assert policy.doc_type_hint is not None
    assert policy.doc_type_hint.value == "bank_statement"
    assert not hasattr(policy, "output")
    assert not hasattr(policy, "resource")
    assert not hasattr(policy, "cache_policy")


def test_parse_policy_fingerprint_changes_only_with_fact_options():
    base = normalize_parse_policy(mode="fast")
    same = normalize_parse_policy(mode="fast")
    different = normalize_parse_policy(mode="forensic")
    assert base.fingerprint() == same.fingerprint()
    assert base.fingerprint() != different.fingerprint()


def test_ocr_page_split_and_locale_are_fact_policy():
    policy = normalize_parse_policy(
        ocr="force",
        ocr_correction="suggest",
        ocr_locale="zh-CN",
        page_split="force",
    )
    assert policy.ocr == "force"
    assert policy.ocr_correction == "suggest"
    assert policy.ocr_language == "zh"
    assert policy.ocr_country == "CN"
    assert policy.page_split == "force"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"page_split": "maybe"}, "unsupported page split mode"),
        ({"ocr_correction": "aggressive"}, "unsupported OCR correction mode"),
        ({"ocr_language": "en", "ocr_locale": "zh-CN"}, "conflicts with locale"),
    ],
)
def test_invalid_fact_policy_options_are_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        normalize_parse_policy(**kwargs)


def test_parse_policy_default_is_minimal():
    assert ParsePolicy().mode == "auto"
