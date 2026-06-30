# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mirror API meta SSOT — LTQG, quarantine, dual_view, plugin_document_type."""

from __future__ import annotations

from docmirror.evidence.spe_consumer import mirror_api_meta_fields
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ParserInfo


def test_mirror_api_meta_fields_ltqg_and_quarantine():
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="bank_statement",
            domain_specific={
                "plugin_document_type": "bank_statement",
                "mirror_quarantined_physical_count": 2,
            },
        ),
        parser_info=ParserInfo(
            structure={
                "ltqg_enabled": True,
                "ltqg_expected_data_rows": 47,
                "ltqg_passed_tables": 1,
                "ltqg_skipped_tables": 0,
                "ltqg_export_logical_tables": 1,
                "ltqg_raw_max_rows": 120,
                "physical_table_count": 5,
                "dual_view": True,
                "quarantined_physical_count": 2,
            }
        ),
    )
    meta = mirror_api_meta_fields(pr)
    assert meta["dual_view"] is True
    assert meta["plugin_document_type"] == "bank_statement"
    assert meta["mirror_expected_data_rows"] == 47
    assert meta["ltqg"]["raw_max_rows"] == 120
    assert meta["quarantine"]["physical_count"] == 2


def test_to_mirror_json_vnext_includes_mirror_meta_ssot():
    pr = ParseResult(
        entities=DocumentEntities(document_type="bank_statement"),
        parser_info=ParserInfo(
            structure={
                "ltqg_enabled": True,
                "ltqg_expected_data_rows": 10,
                "ltqg_passed_tables": 1,
                "ltqg_skipped_tables": 0,
                "physical_table_count": 5,
                "dual_view": True,
            }
        ),
    )
    api = pr.to_mirror_json_vnext()
    assert "meta" not in api
    assert api["source"]["provenance"]["parser_info"]["structure"]["physical_table_count"] == 5
    meta = mirror_api_meta_fields(pr)
    assert meta["physical_table_count"] == 5
    assert meta["dual_view"] is True
    assert meta["ltqg"]["expected_data_rows"] == 10
    assert meta["mirror_expected_data_rows"] == 10
