# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Design 21 Mirror JSON serialization contract tests."""

from __future__ import annotations

import json
from pathlib import Path

from docmirror.models.entities.parse_result import (
    CellValue,
    DocumentEntities,
    LogicalTable,
    PageContent,
    ParserInfo,
    ParseResult,
    RowType,
    TableBlock,
    TableRow,
)
from docmirror.models.schemas.registry import validate_projection_payload
from docmirror.models.mirror.serialization_contract import (
    MIRROR_CONTRACT_VERSION,
    build_count_reconciliation,
    enrich_physical_table_dict,
    is_prose_disclaimer_table,
    link_blocks_to_tables,
    logical_table_role,
)


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "docmirror/configs/schemas/mirror.schema.json"


def test_mirror_schema_file_exists():
    path = _schema_path()
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["title"] == "DocMirror Mirror JSON"
    assert "mirror_profile" in data["properties"]


def test_enrich_physical_table_ssot_fields():
    table = enrich_physical_table_dict(
        {
            "table_id": "p1_t0",
            "headers": ["日期", "金额"],
            "rows": [{"cells": [{"text": "2024-01-01"}, {"text": "100"}]}],
        }
    )
    assert table["ssot"] == "raw_rows"
    assert table["navigation_ref"] == "table:p1_t0"
    assert table["content_role"] == "ledger"
    assert table["raw_rows"][0] == ["日期", "金额"]
    assert table["header_source"] in {"vocabulary_match", "inherited", "data_row", "none"}


def test_prose_disclaimer_header_source():
    headers = ["1.本证明", "仅证明在用户选择", "的交易类型和时间"]
    raw_rows = [headers, ["2.因系统", "原因或通讯故障等"]]
    assert is_prose_disclaimer_table(headers, raw_rows) is True
    table = enrich_physical_table_dict(
        {"table_id": "p44_t0", "headers": headers, "raw_rows": raw_rows, "page": 44},
        page_number=44,
        annex_pages={44},
    )
    assert table["header_source"] == "prose_block"
    assert table["content_role"] == "annex"


def test_link_blocks_to_tables_bidirectional():
    tables = [{"table_id": "pt_1_0", "navigation_ref": "table:pt_1_0"}]
    blocks = [{"block_id": "blk_p1_tbl0", "morphology": "S2", "ref": "table:pt_1_0"}]
    linked = link_blocks_to_tables(blocks, tables)
    assert linked[0]["navigation_ref"] == "table:pt_1_0"
    assert tables[0]["block_ref"] == "blk_p1_tbl0"


def test_count_reconciliation():
    counts = {
        "physical_data_rows": 1376,
        "logical_data_rows_export": 1409,
    }
    lt_primary = LogicalTable(
        table_id="main",
        merge_method="cross_page_continuation",
        quality_passed=True,
        source_pages=[1, 2],
        row_count=1409,
    )
    lt_annex = LogicalTable(
        table_id="annex",
        merge_method="quarantine_standalone",
        quality_passed=False,
        source_pages=[44],
        row_count=9,
    )
    pages = [
        {"page_number": 1, "tables": [{"row_count": 30}]},
        {"page_number": 44, "tables": [{"row_count": 9}]},
    ]
    recon = build_count_reconciliation(
        counts=counts,
        logical_tables=[lt_primary, lt_annex],
        pages=pages,
    )
    assert recon["annex_data_rows"] == 9
    assert recon["physical_rows_in_export_pages"] == 30
    assert recon["cross_page_merge_adjustment"] == 1409 - 30


def test_logical_table_role_annex():
    lt = LogicalTable(
        table_id="annex_1",
        merge_method="quarantine_standalone",
        quality_passed=False,
        quality_skip_reason="col_count_mismatch",
    )
    assert logical_table_role(lt) == "annex"


def test_to_api_dict_design21_contract_fields():
    page_table = TableBlock(
        table_id="p1_t0",
        headers=["A", "B"],
        page=1,
        metadata={"raw_rows": [["A", "B"], ["1", "2"]]},
    )
    page_table.rows.append(
        TableRow(cells=[CellValue(text="1"), CellValue(text="2")], row_type=RowType.DATA)
    )
    pr = ParseResult(
        pages=[PageContent(page_number=1, tables=[page_table])],
        entities=DocumentEntities(
            document_type="bank_reconciliation",
            domain_specific={"layout_profile_id": "borderless_ledger_bank"},
        ),
        logical_tables=[
            LogicalTable(
                table_id="main",
                merge_method="cross_page_continuation",
                quality_passed=True,
                source_pages=[1, 2],
            ),
            LogicalTable(
                table_id="annex",
                merge_method="quarantine_standalone",
                quality_passed=False,
                quality_skip_reason="col_count_mismatch",
                source_pages=[219],
            ),
        ],
        parser_info=ParserInfo(
            structure={
                "primary": "table_led",
                "layout_profile_id": "borderless_ledger_bank",
                "dual_view": True,
                "quarantined_physical_count": 1,
            }
        ),
    )
    api = pr.to_api_dict(mirror_level="standard")
    assert api["mirror_profile"]["contract_version"] == MIRROR_CONTRACT_VERSION
    assert api["mirror_profile"]["level"] == "standard"
    assert MIRROR_CONTRACT_VERSION == "1.1"
    counts = api["meta"]["counts"]
    assert counts["logical_tables_total"] == 2
    assert counts["logical_tables_export"] == 1
    assert counts["logical_tables_annex"] == 1
    assert api["meta"]["logical_table_count"] == counts["logical_tables_export"]
    assert "reconciliation" in counts
    assert "cross_page_merge_adjustment" in counts["reconciliation"]
    identity = api["data"]["document"]["identity"]
    assert identity["scene_hint"] == "bank_reconciliation"
    assert identity["layout_profile_id"] == "borderless_ledger_bank"
    assert identity["plugin_domain_hint"] == "bank_statement"
    assert "layout_profile_id" not in api["data"]["document"]["properties"]
    structure = api["meta"]["structure"]
    assert structure["quarantine"]["logical_annex_count"] == 1
    assert structure.get("morphology_aggregate_ref") == "document.morphology_stats"
    assert "page_morphology_stats" not in structure
    lts = api["data"]["document"]["logical_tables"]
    assert lts[0]["role"] == "primary"
    assert lts[1]["role"] == "annex"
    assert lts[1]["composition"]["topology"] == "annex"
    pages = api["data"]["document"]["pages"]
    assert pages[0]["tables"][0]["ssot"] == "raw_rows"
    assert pages[0]["tables"][0]["navigation_ref"] == "table:p1_t0"


def test_to_api_dict_always_exports_structure_ssot():
    pr = ParseResult()
    api = pr.to_api_dict(mirror_level="standard")

    assert "counts" in api["meta"]
    assert "structure" in api["meta"]
    assert api["meta"]["structure"]["counts"] == api["meta"]["counts"]
    assert api["meta"]["structure"]["quarantine"] == {
        "physical_count": 0,
        "logical_annex_count": 0,
        "annex_logical_tables": [],
    }
    assert validate_projection_payload("mirror", api).valid is True


def test_to_api_dict_quarantine_ssot_is_meta_structure():
    pr = ParseResult(
        entities=DocumentEntities(document_type="bank_statement"),
        parser_info=ParserInfo(
            structure={
                "primary": "table_led",
                "quarantined_physical_count": 2,
            }
        ),
    )
    api = pr.to_api_dict(mirror_level="standard")

    assert "quarantine" not in api["meta"]
    assert api["meta"]["structure"]["quarantine"]["physical_count"] == 2


def test_cell_standard_audit_fields():
    pr = ParseResult()
    cell = CellValue(text="x", geometry_status="exact")
    cell.source_cell_refs = ["c0"]
    d = pr._serialize_cell(cell, forensic=False)
    assert d["data_type"] == "text"
    assert d["geometry_status"] == "exact"
    assert d["source_cell_refs"] == ["c0"]
