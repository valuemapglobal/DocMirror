# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Quarantine annex in debug / forensic API meta."""

from __future__ import annotations

from docmirror.evidence.spe_consumer import mirror_quarantine_annex_fields
from docmirror.models.entities.parse_result import ParseResult, ParserInfo


def test_quarantine_annex_hidden_in_standard_mode():
    pr = ParseResult(
        parser_info=ParserInfo(
            structure={
                "quarantined_physical_tables": [{"page": 4, "reason": "col_count_mismatch"}],
            }
        )
    )
    assert mirror_quarantine_annex_fields(pr, mirror_level="standard") == {}


def test_quarantine_annex_in_forensic_mode():
    pr = ParseResult(
        parser_info=ParserInfo(
            structure={
                "quarantined_physical_tables": [{"page": 4, "reason": "col_count_mismatch"}],
                "quarantined_logical_tables_annex": [{"logical_id": "lt_bad"}],
            }
        )
    )
    annex = mirror_quarantine_annex_fields(pr, mirror_level="forensic")
    assert len(annex["quarantined_tables"]) == 1
    assert annex["quarantined_logical_tables"][0]["logical_id"] == "lt_bad"
