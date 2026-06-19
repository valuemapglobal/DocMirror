# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for bank BLO + CQF pipeline."""

from __future__ import annotations

from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin
from docmirror.plugins.bank_statement.extract_pipeline import run_bank_statement_extract
from tests.unit.test_pipe_text_table_builder import _synthetic_boc_text


def test_blo_pipe_text_cqf_success():
    plugin = BankStatementCommunityPlugin()
    result = run_bank_statement_extract(None, _synthetic_boc_text(), plugin)
    assert result.style_meta.extract_status == "success"
    assert result.style_meta.canonical_extracted >= 1
    assert result.records
