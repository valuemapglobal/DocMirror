# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for shared bank statement extract pipeline."""

from __future__ import annotations

from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin
from docmirror.plugins.bank_statement.extract_pipeline import (
    enrich_identity_fields,
    run_bank_statement_extract,
)
from tests.unit.test_pipe_text_table_builder import _synthetic_boc_text


def test_enrich_identity_fields_from_header():
    text = _synthetic_boc_text()
    fields = enrich_identity_fields({}, text)
    assert fields["account_holder"]["normalized_value"] == "南京创沃电气设备有限公司"


def test_run_bank_statement_extract_pipe_text():
    plugin = BankStatementCommunityPlugin()
    text = _synthetic_boc_text()
    result = run_bank_statement_extract(None, text, plugin)
    assert result.style_meta.reconstruction_source == "pipe_text"
    assert result.style_meta.extracted_rows >= 1
    assert "account_holder" in result.identity_fields
