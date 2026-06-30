# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Product contract tests — four-file output separation (04 CLI redesign)."""

from __future__ import annotations

import importlib
import json

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
from docmirror.server.edition_outputs import build_all_projections, write_four_files
from tests.contract.test_edition_schema_conformance import check_community

_FORBIDDEN_MIRROR_KEYS = frozenset({"records", "mirror_ref", "edition"})


def _minimal_mirror(document_type: str = "business_license") -> ParseResult:
    pr = ParseResult(status=ResultStatus.SUCCESS)
    pr.entities = DocumentEntities(document_type=document_type)
    return pr


def test_mirror_output_has_no_plugin_records():
    result = _minimal_mirror()
    outputs = build_all_projections(result, full_text="")
    mirror = outputs["mirror"]
    # Mirror API must not embed edition plugin payloads
    assert "editions" not in mirror.get("data", {})
    assert "mirror_ref" not in mirror


def test_written_vnext_mirror_keeps_canonical_top_level_clean(tmp_path):
    result = _minimal_mirror()

    _, written = write_four_files(
        result,
        tmp_path,
        task_id="task_clean_top",
        editions=("mirror",),
        overwrite=True,
    )

    mirror = json.loads(written["mirror"].read_text(encoding="utf-8"))
    assert set(mirror) == {
        "mirror",
        "source",
        "document",
        "pages",
        "evidence",
        "regions",
        "blocks",
        "graph",
        "semantics",
        "quality",
        "diagnostics",
        "assets",
    }
    assert "metadata" not in mirror
    assert "meta" not in mirror
    assert "data" not in mirror
    assert mirror["source"]["provenance"]["output_ids"] == {
        "task_id": "task_clean_top",
        "file_id": "001",
    }


def test_written_mirror_runs_verification_crop_ocr_hook(tmp_path, monkeypatch):
    import docmirror.geometry.verification.crops as crop_hooks
    import docmirror.server.edition_outputs as edition_outputs

    result = _minimal_mirror()
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    mirror_payload = {
        "mirror": {"schema": "docmirror.mirror_json"},
        "source": {"provenance": {}},
        "document": {},
        "pages": [],
        "evidence": {"text_atoms": [], "image_atoms": [], "vector_atoms": []},
        "regions": [],
        "blocks": [],
        "graph": {"nodes": [], "edges": []},
        "semantics": {},
        "quality": {"verification": {"units": []}, "gates": []},
        "diagnostics": {"pipeline": []},
        "assets": {"items": []},
    }

    def fake_build_all_projections(*_args, **_kwargs):
        return {"mirror": mirror_payload}

    def fake_attach_crop_assets(mirror, **_kwargs):
        asset = {
            "id": "asset:verification_crop:fake",
            "kind": "verification_unit_crop",
            "path": "assets/verification_crops/fake.png",
            "unit_id": "unit:fake",
        }
        mirror["assets"]["items"].append(asset)
        mirror["quality"]["verification"]["crop_artifact_count"] = 1
        return [asset]

    def fake_attach_crop_ocr(mirror, **_kwargs):
        mirror["assets"]["items"][0]["ocr"] = {"status": "verified", "engine": "fake", "text": "42"}
        mirror["quality"]["verification"]["crop_ocr"] = {
            "status": "ok",
            "processed_count": 1,
            "candidate_count": 1,
            "agreement_count": 1,
            "conflict_count": 0,
            "not_evaluated_count": 0,
        }
        mirror["quality"]["gates"].append({"id": "gate:verification_crop_ocr", "status": "pass"})

    monkeypatch.setattr(edition_outputs, "build_all_projections", fake_build_all_projections)
    monkeypatch.setattr(crop_hooks, "attach_verification_crop_assets", fake_attach_crop_assets)
    monkeypatch.setattr(crop_hooks, "attach_unit_crop_ocr_candidates", fake_attach_crop_ocr)

    _, written = edition_outputs.write_four_files(
        result,
        tmp_path,
        file_path=str(pdf_path),
        task_id="task_crop_ocr",
        editions=("mirror",),
        overwrite=True,
        artifact_pack=True,
    )

    mirror = json.loads(written["mirror"].read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "task_crop_ocr" / "manifest.json").read_text(encoding="utf-8"))
    assert mirror["assets"]["items"][0]["ocr"]["status"] == "verified"
    assert mirror["quality"]["verification"]["crop_ocr"]["agreement_count"] == 1
    assert any(gate["id"] == "gate:verification_crop_ocr" and gate["status"] == "pass" for gate in mirror["quality"]["gates"])
    assert manifest["artifacts"]["verification_crops"] == "assets/verification_crops"
    assert manifest["verification_crop_count"] == 1


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

    outputs = build_all_projections(
        result,
        include_text=True,
        mirror_level="forensic",
        request_id="req_contract",
    )

    mirror = outputs["mirror"]
    page = mirror["pages"][0]
    text_atoms = mirror["evidence"]["text_atoms"]
    text_atom = next(atom for atom in text_atoms if atom["text"] == "Visible title")
    table = next(block for block in mirror["blocks"] if block["type"] == "table")
    grid = table["content"]["grid"]
    data_cell = next(cell for cell in grid["cells"] if cell["text"] == "42")
    assert "request_id" not in mirror
    assert "timestamp" not in mirror
    assert "meta" not in mirror
    assert mirror["mirror"]["profile"] == "forensic"
    assert page["width"] == 612
    assert page["height"] == 792
    assert text_atom["bbox"] == [1, 2, 3, 4]
    assert text_atom["source_refs"] == ["txt-1"]
    assert table["bbox"] == [10, 20, 30, 40]
    assert table["provenance"]["source_table_id"] == "pt_1_0"
    assert table["quality"]["grid_confidence"] >= 0.9
    assert grid["columns"][0]["header"] == "A"
    assert data_cell["value"]["normalized"] == 42.0
    assert data_cell["bbox"] == [5, 6, 7, 8]
    assert mirror["quality"]["coverage"]["text_conservation_score"] == 1.0
    assert mirror["quality"]["tables"]["count"] == 1
    assert any(gate["id"] == "gate:token_conservation" for gate in mirror["quality"]["gates"])


def test_mirror_conservation_reports_empty_tables_without_reason():
    result = _minimal_mirror()
    outputs = build_all_projections(result)
    mirror = outputs["mirror"]
    assert "meta" not in mirror
    gate_ids = {gate["id"] for gate in mirror["quality"]["gates"]}
    assert {"gate:evidence_plane_built", "gate:residual_ratio", "gate:token_conservation"} <= gate_ids
    assert mirror["quality"]["coverage"]["residual_ratio"] >= 0.0


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

    mirror = build_all_projections(result, mirror_level="forensic")["mirror"]
    assert "meta" not in mirror
    assert mirror["mirror"]["profile"] == "forensic"
    table = next(block for block in mirror["blocks"] if block["type"] == "table")
    assert table["provenance"]["source_table_id"] == "pt_1_0"
    assert mirror["source"]["provenance"]["pipeline_debug"]["extraction_audit"]["pages"][0]["picked"] == "pdfplumber_default"


def test_bridge_projects_text_span_evidence_into_forensic_ehl():
    from docmirror.input.bridge.parse_result_bridge import ParseResultBridge
    from docmirror.models.entities.physical import BaseResult, Block, PageLayout, TextSpan

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
    api = mirror.to_mirror_json_vnext(mirror_level="forensic")
    assert "meta" not in api
    assert api["mirror"]["profile"] == "forensic"
    atoms = api["evidence"]["text_atoms"]
    assert atoms[0]["text"] == "hello world"
    assert atoms[0]["source_refs"] == ["text_p1_b1_span0", "text_p1_b1_span1"]


def test_community_mirror_document_type_consistency():
    result = _minimal_mirror("business_license")
    outputs = build_all_projections(result)
    comm = outputs.get("community")
    if comm is None:
        pytest.skip("no community output")
    mirror_type = outputs["mirror"].get("document", {}).get("document_type")
    comm_type = comm.get("document", {}).get("document_type")
    assert comm_type == mirror_type or comm_type == "business_license"


def test_enterprise_not_generated_when_package_missing():
    try:
        importlib.import_module("docmirror_enterprise")
    except ImportError:
        outputs = build_all_projections(_minimal_mirror())
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
    assert out["document"]["archetype"] == "key_value_document"


def test_mirror_only_envelope_for_enterprise_only_type():
    from docmirror.plugins._runtime.runner import run_plugin_extract_sync

    result = _minimal_mirror("audit_report")
    out = run_plugin_extract_sync(result, edition="community")
    assert out is not None
    assert out["plugin"]["name"] == "generic"
    assert "community_generic_fallback" in out["status"]["warnings"]
    assert out["classification"]["matched_document_type"] == "audit_report"


def test_generic_envelope_for_demoted_type():
    from docmirror.plugins._runtime.runner import run_plugin_extract_sync

    result = _minimal_mirror("id_card")
    result.entities.domain_specific = {"name": "张三"}
    out = run_plugin_extract_sync(result, edition="community")
    assert out is not None
    assert out["plugin"]["name"] == "generic"
    assert out["document"]["archetype"] == "key_value_document"
    assert "community_generic_fallback" in out["status"]["warnings"]
    assert not check_community(out)


def test_generic_fallback_envelope_for_demoted_type():
    from docmirror.plugins._runtime.runner import run_plugin_extract_sync

    result = _minimal_mirror("id_card")
    result.entities.domain_specific = {"name": "Example Name"}
    out = run_plugin_extract_sync(result, edition="community")
    assert out is not None
    assert out["plugin"]["name"] == "generic"
    assert out["classification"]["matched_document_type"] == "id_card"
    assert "community_generic_fallback" in out["status"]["warnings"]


def test_perceive_result_envelope_no_edition_on_mirror():
    from docmirror.input.entry.perceive_result import PerceiveResult

    mirror = _minimal_mirror()
    env = PerceiveResult(mirror=mirror, editions={"community": {"edition": "community"}})
    assert env.mirror is mirror
    assert env.editions["community"]["edition"] == "community"
    assert "_edition_outputs" not in (mirror.entities.domain_specific or {})
