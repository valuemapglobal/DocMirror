# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Product contract tests — four-file output separation (04 CLI redesign)."""

from __future__ import annotations

import importlib

import pytest

pytestmark = [pytest.mark.tier_contract]

from docmirror.models.entities.parse_result import (
    CellValue,
    DocumentEntities,
    PageContent,
    ParseResult,
    ResultStatus,
    TableBlock,
    TableRow,
    TextBlock,
)
from docmirror.server.edition_outputs import build_all_edition_outputs
from tests.contract.test_edition_schema_conformance import check_community

_FORBIDDEN_MIRROR_KEYS = frozenset({"records", "mirror_ref", "edition"})


def _minimal_mirror(document_type: str = "business_license") -> ParseResult:
    pr = ParseResult(status=ResultStatus.SUCCESS)
    pr.entities = DocumentEntities(document_type=document_type)
    return pr


def test_mirror_output_has_no_plugin_records():
    result = _minimal_mirror()
    outputs = build_all_edition_outputs(result, full_text="")
    mirror = outputs["mirror"]
    # Mirror API must not embed edition plugin payloads
    assert "editions" not in mirror.get("data", {})
    assert "mirror_ref" not in mirror


def test_mirror_forensic_output_preserves_projection_controls():
    result = _minimal_mirror()
    result.raw_text = "RAW Visible title\nRAW table text"
    result.pages = [
        PageContent(
            page_number=1,
            width=612,
            height=792,
            texts=[TextBlock(content="Visible title", bbox=[1, 2, 3, 4], evidence_ids=["txt-1"])],
            tables=[
                TableBlock(
                    table_id="pt_1_0",
                    headers=["A"],
                    rows=[TableRow(cells=[CellValue(text="42", cleaned="42", numeric=42.0, bbox=[5, 6, 7, 8])])],
                    bbox=[10, 20, 30, 40],
                    extraction_layer="vector_table",
                    extraction_confidence=0.91,
                    evidence_ids=["tbl-1"],
                    metadata={
                        "zone_type": "data_table",
                        "merged_cells": [{"row": 0, "col": 0, "rowspan": 1, "colspan": 2}],
                    },
                )
            ],
        )
    ]

    outputs = build_all_edition_outputs(
        result,
        include_text=True,
        mirror_level="forensic",
        request_id="req_contract",
    )

    mirror = outputs["mirror"]
    document = mirror["data"]["document"]
    page = document["pages"][0]
    page_texts = (page.get("flow") or {}).get("texts") or page.get("texts") or []
    table = page["tables"][0]
    assert mirror["request_id"] == "req_contract"
    assert document["text"].startswith("Visible title")
    assert document["raw_text"].startswith("RAW Visible title")
    assert document["raw_text_format"] == "plain"
    assert page["width"] == 612
    assert page["height"] == 792
    assert page_texts[0]["bbox"] == [1, 2, 3, 4]
    assert page_texts[0]["evidence_ids"] == ["txt-1"]
    assert table["bbox"] == [10, 20, 30, 40]
    assert table["extraction_layer"] == "vector_table"
    assert table["extraction_confidence"] == 0.91
    assert table["evidence_ids"] == ["tbl-1"]
    assert table["metadata"]["zone_type"] == "data_table"
    assert table["metadata"]["merged_cells"][0]["colspan"] == 2
    assert table["rows"][0]["cells"][0]["numeric"] == 42.0
    assert table["rows"][0]["cells"][0]["bbox"] == [5, 6, 7, 8]
    assert mirror["meta"]["conservation"]["passed"] is True
    assert mirror["meta"]["conservation"]["metrics"]["evidence_span_count"] >= 2
    assert mirror["meta"]["ehl"]["evidence_summary"]["total_spans"] >= 2
    assert any(h["kind"] == "table" for h in mirror["meta"]["ehl"]["hypotheses"])


def test_mirror_conservation_reports_empty_tables_without_reason():
    result = _minimal_mirror()
    outputs = build_all_edition_outputs(result)
    conservation = outputs["mirror"]["meta"]["conservation"]
    assert conservation["passed"] is False
    assert any(issue["code"] == "empty_tables_without_reason" for issue in conservation["issues"])


def test_forensic_ehl_includes_bcs_selected_and_rejected_candidates():
    result = _minimal_mirror()
    result.pages = [
        PageContent(
            page_number=1,
            tables=[
                TableBlock(
                    table_id="pt_1_0",
                    headers=["A"],
                    rows=[TableRow(cells=[CellValue(text="1")])],
                    extraction_layer="pdfplumber_default",
                )
            ],
        )
    ]
    from docmirror.models.ehl import attach_pipeline_debug

    attach_pipeline_debug(
        result,
        "extraction_audit",
        {
            "profile_id": "ledger",
            "pages": [
                {
                    "page": 1,
                    "picked": "pdfplumber_default",
                    "score": 0.93,
                    "candidates": [
                        {"layer": "pipe_delimited", "rows": 3, "conf": 0.7},
                        {"layer": "pdfplumber_default", "rows": 4, "conf": 0.9},
                    ],
                }
            ],
        },
    )

    mirror = build_all_edition_outputs(result, mirror_level="forensic")["mirror"]
    bcs = [h for h in mirror["meta"]["ehl"]["hypotheses"] if h["method"] == "bcs"]
    assert len(bcs) == 2
    assert any(h["layer"] == "pdfplumber_default" and h["selected"] for h in bcs)
    assert any(h["layer"] == "pipe_delimited" and not h["selected"] for h in bcs)


def test_bridge_projects_text_span_evidence_into_forensic_ehl():
    from docmirror.core.bridge.parse_result_bridge import ParseResultBridge
    from docmirror.core.physical.models import BaseResult, Block, PageLayout, TextSpan

    base = BaseResult(
        pages=(
            PageLayout(
                page_number=1,
                blocks=(
                    Block(
                        block_id="b1",
                        block_type="text",
                        page=1,
                        bbox=(0, 0, 100, 20),
                        raw_content="hello world",
                        spans=(
                            TextSpan(text="hello", bbox=(0, 0, 40, 20)),
                            TextSpan(text="world", bbox=(45, 0, 100, 20)),
                        ),
                    ),
                ),
            ),
        ),
        full_text="hello world",
    )

    mirror = ParseResultBridge.from_base_result(base)
    api = mirror.to_api_dict(mirror_level="forensic")
    page = api["data"]["document"]["pages"][0]
    page_texts = (page.get("flow") or {}).get("texts") or page.get("texts") or []
    text = page_texts[0]
    summary = api["meta"]["ehl"]["evidence_summary"]
    assert text["evidence_ids"] == ["text_p1_b1_span0", "text_p1_b1_span1"]
    assert summary["total_spans"] >= 2
    assert summary["by_source"]["pdf_text"] >= 2


def test_community_mirror_document_type_consistency():
    result = _minimal_mirror("business_license")
    outputs = build_all_edition_outputs(result)
    comm = outputs.get("community")
    if comm is None:
        pytest.skip("no community output")
    mirror_type = outputs["mirror"].get("data", {}).get("document", {}).get("document_type")
    comm_type = comm.get("document", {}).get("document_type")
    assert comm_type == mirror_type or comm_type == "business_license"


def test_enterprise_not_generated_when_package_missing():
    try:
        importlib.import_module("docmirror_enterprise")
    except ImportError:
        outputs = build_all_edition_outputs(_minimal_mirror())
        assert outputs["enterprise"] is None
        return
    pytest.skip("docmirror_enterprise installed — skip missing-package assertion")


def test_generic_community_envelope_conforms():
    from docmirror.plugins.generic.community_plugin import plugin

    mirror = ParseResult(status=ResultStatus.SUCCESS)
    mirror.entities = DocumentEntities(document_type="id_card")
    mirror.entities.domain_specific = {"name": "测试", "id_number": "110101199001011234"}

    out = plugin.extract_from_mirror(mirror)
    errors = check_community(out)
    assert errors == [], f"generic envelope errors: {errors}"
    assert out["plugin"]["name"] == "generic"
    assert out["document"]["archetype"] == "generic_mirror"


def test_mirror_only_envelope_for_enterprise_only_type():
    from docmirror.plugins.runner import run_plugin_extract_sync

    result = _minimal_mirror("audit_report")
    out = run_plugin_extract_sync(result, edition="community")
    assert out is not None
    assert "mirror_only:no_community_plugin" in out["status"]["warnings"]
    assert out.get("mirror_ref", {}).get("document_type") == "audit_report"


def test_generic_envelope_for_demoted_type():
    from docmirror.plugins.runner import run_plugin_extract_sync

    result = _minimal_mirror("id_card")
    result.entities.domain_specific = {"name": "张三"}
    out = run_plugin_extract_sync(result, edition="community")
    assert out is not None
    assert out["plugin"]["name"] == "generic"
    assert out["document"]["archetype"] == "generic_mirror"
    assert "community_generic_fallback" in out["status"]["warnings"]
    assert not check_community(out)


def test_generic_fallback_envelope_for_demoted_type():
    from docmirror.plugins.runner import run_plugin_extract_sync

    result = _minimal_mirror("id_card")
    result.entities.domain_specific = {"name": "ZhangSan"}
    out = run_plugin_extract_sync(result, edition="community")
    assert out is not None
    assert out["plugin"]["name"] == "generic"
    assert out["classification"]["matched_document_type"] == "id_card"
    assert "community_generic_fallback" in out["status"]["warnings"]


def test_perceive_result_envelope_no_edition_on_mirror():
    from docmirror.core.entry.perceive_result import PerceiveResult

    mirror = _minimal_mirror()
    env = PerceiveResult(mirror=mirror, editions={"community": {"edition": "community"}})
    assert env.mirror is mirror
    assert env.editions["community"]["edition"] == "community"
    assert "_edition_outputs" not in (mirror.entities.domain_specific or {})
