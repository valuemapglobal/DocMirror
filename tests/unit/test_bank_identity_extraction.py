# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bank statement identity field extraction tests."""

from __future__ import annotations

from docmirror.models.entities.parse_result import DocumentEntities, KeyValuePair, PageContent, ParseResult
from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin
from docmirror.plugins.bank_statement.extract_pipeline import enrich_identity_fields


def test_extract_identity_matches_账户号_kv():
    plugin = BankStatementCommunityPlugin()
    pr = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                key_values=[KeyValuePair(key="账户号", value="03-869900040010370")],
            )
        ]
    )
    fields = plugin._extract_identity(pr)
    assert fields["account_number"]["normalized_value"] == "03-869900040010370"


def test_enrich_identity_maps_subject_id_to_account_number():
    pr = ParseResult(
        entities=DocumentEntities(
            organization="中国农业银行",
            subject_id="03-869900040010370",
        )
    )
    fields = enrich_identity_fields({}, "", pr, institution="中国农业银行")
    assert fields["bank_name"]["normalized_value"] == "中国农业银行"
    assert fields["account_number"]["normalized_value"] == "03-869900040010370"
