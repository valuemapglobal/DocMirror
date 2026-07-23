# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ParsePolicy is adapter-independent canonical input."""

from docmirror.input.canonical import attach_parse_policy
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult


def test_force_document_type_overrides_competing_adapter_fact_before_classification():
    result = ParseResult(entities=DocumentEntities(document_type="alipay_payment"))

    attach_parse_policy(
        result,
        doc_type_hint="bank_statement",
        doc_type_hint_strength="force",
        parse_policy={"mode": "balanced"},
        parse_policy_fingerprint="policy-sha",
    )

    assert result.entities.document_type == "bank_statement"
    assert result.entities.domain_specific["user_doc_type_hint"] == "bank_statement"
    assert result.entities.domain_specific["user_doc_type_hint_strength"] == "force"
    assert result.parser_info.options["parse_policy_fingerprint"] == "policy-sha"
    assert any(
        mutation.middleware_name == "ParsePolicy" and mutation.field_changed == "entities.document_type"
        for mutation in result.mutations
    )


def test_prefer_document_type_remains_evidence_only():
    result = ParseResult(entities=DocumentEntities(document_type="alipay_payment"))

    attach_parse_policy(
        result,
        doc_type_hint="bank_statement",
        doc_type_hint_strength="prefer",
    )

    assert result.entities.document_type == "alipay_payment"
    assert result.entities.domain_specific["user_doc_type_hint"] == "bank_statement"
    assert not result.mutations
