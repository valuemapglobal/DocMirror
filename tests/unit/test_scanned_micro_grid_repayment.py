# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json

import docmirror.plugins.credit_report.repayment_grid as repayment_mod
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult
from docmirror.models.mirror.page_evidence_bundles import (
    domain_specific_with_page_bundles,
    materialize_micro_grids_from_bundles,
    merge_micro_grid_structures_into_bundles,
    micro_grid_structures_from_bundles,
    page_evidence_bundle,
)
from docmirror.ocr.micro_grid.cell_recognition import normalize_allowlist_text
from docmirror.ocr.micro_grid.detect import detect_micro_grid_candidates
from docmirror.ocr.micro_grid.models import OCRToken
from docmirror.plugins._base.kv_community_enrich import enrich_credit_report_output
from docmirror.plugins.credit_report.repayment_grid import (
    extract_credit_repayment_records,
    records_from_micro_grid_dict,
)
from docmirror.server.edition_outputs import build_all_projections, write_four_files


def _micro_grid_bundle_domain(
    *,
    page: int = 4,
    page_width: int = 834,
    page_height: int = 1207,
    lines=None,
    tokens=None,
    **extra,
):
    lines = lines if lines is not None else _credit_page4_lines()
    tokens = tokens if tokens is not None else [token.to_dict() for token in _credit_page4_tokens()]
    ds = domain_specific_with_page_bundles(
        page_evidence_bundle(
            page,
            page_width=page_width,
            page_height=page_height,
            micro_grid_evidence={
                "page": page,
                "page_width": page_width,
                "page_height": page_height,
                "lines": lines,
                "tokens": tokens,
            },
        ),
        **extra,
    )
    materialize_micro_grids_from_bundles(ds)
    return ds


def _credit_page4_lines():
    return [
        {
            "content": "2020年09月-2021年02月的还款记录",
            "bbox": [280.46, 194.67, 510.65, 217.78],
            "confidence": 1.0,
        },
        {
            "content": "1 122689 113.45710",
            "bbox": [130.84, 222.65, 733.57, 241.51],
            "confidence": 1.0,
        },
        {
            "content": "CN.",
            "bbox": [136.90, 249.42, 206.56, 267.06],
            "confidence": 1.0,
        },
        {
            "content": "2021",
            "bbox": [75.71, 262.80, 112.67, 280.44],
            "confidence": 1.0,
        },
        {
            "content": "NN N N",
            "bbox": [559.11, 302.34, 731.75, 319.38],
            "confidence": 1.0,
        },
        {
            "content": "2020",
            "bbox": [75.11, 315.12, 109.64, 332.76],
            "confidence": 1.0,
        },
        {
            "content": "000 0",
            "bbox": [561.53, 327.89, 729.93, 345.54],
            "confidence": 1.0,
        },
    ]


def _credit_page4_tokens():
    tokens = []
    for idx, line in enumerate(_credit_page4_lines()):
        x0, y0, x1, y1 = line["bbox"]
        tokens.append(
            OCRToken(
                token_id=f"ocr_p4_t{idx}",
                text=line["content"],
                bbox=(x0, y0, x1, y1),
                confidence=line["confidence"],
                page=4,
                source="rapidocr_test",
                raw_bbox=(x0 * 2, y0 * 2, x1 * 2, y1 * 2),
            )
        )
    return tokens


def _record_tuples(records):
    return [(r["year"], r["month"], r["status"], r["overdue_amount"]) for r in records]


def _expected_repayment_tuples():
    return [
        (2021, 1, "N", "0"),
        (2021, 2, "C", "0"),
        (2020, 9, "N", "0"),
        (2020, 10, "N", "0"),
        (2020, 11, "N", "0"),
        (2020, 12, "N", "0"),
    ]


def _micro_grid_structure_from_document(document: dict, *, page: int = 4) -> dict:
    from docmirror.models.mirror.page_access import micro_grid_structures_from_document

    for grid in micro_grid_structures_from_document(document):
        if int(grid.get("page") or 0) == page:
            return grid
    return {}


def test_records_from_micro_grid_dict_matches_line_extraction():
    out = extract_credit_repayment_records(_credit_page4_lines(), page=4, tokens=_credit_page4_tokens())
    projected = records_from_micro_grid_dict(out["micro_grid"])
    assert _record_tuples(projected) == _record_tuples(out["repayment_records"])


def test_credit_enrich_from_micro_grids_only_without_scanned_evidence():
    out = extract_credit_repayment_records(_credit_page4_lines(), page=4, tokens=_credit_page4_tokens())
    ds: dict = {}
    merge_micro_grid_structures_into_bundles(ds, [out["micro_grid"]])
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=ds,
        )
    )
    enriched = enrich_credit_report_output({"data": {}}, parse_result=pr)
    assert _record_tuples(enriched["repayment_records"]) == _expected_repayment_tuples()


def test_credit_enrich_skips_smg_rebuild_when_structure_exists(monkeypatch):
    out = extract_credit_repayment_records(_credit_page4_lines(), page=4, tokens=_credit_page4_tokens())
    ds = _micro_grid_bundle_domain()
    merge_micro_grid_structures_into_bundles(ds, [out["micro_grid"]])
    calls: list[int] = []

    def _forbidden_rebuild(*_args, **_kwargs):
        calls.append(1)
        raise AssertionError("SMG rebuild should not run when micro_grid_structures exist")

    monkeypatch.setattr(repayment_mod, "reconstruct_repayment_micro_grid_from_lines", _forbidden_rebuild)
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=ds,
        )
    )
    enriched = enrich_credit_report_output({"data": {}}, parse_result=pr)
    assert calls == []
    assert _record_tuples(enriched["repayment_records"]) == _expected_repayment_tuples()


def test_credit_repayment_micro_grid_from_line_bboxes():
    out = extract_credit_repayment_records(_credit_page4_lines(), page=4)

    assert out["micro_grid"]
    assert len(out["micro_grid"]["col_bands"]) == 13
    assert out["micro_grid"]["col_bands"][0]["role"] == "year"
    year_cells = [
        cell
        for row in out["micro_grid"]["cells"]
        for cell in row
        if cell.get("role") == "year"
    ]
    assert [cell["text"] for cell in year_cells] == ["2021", "2020"]
    assert _record_tuples(out["repayment_records"]) == _expected_repayment_tuples()
    assert all(record["source_cell_refs"] for record in out["repayment_records"])


def test_credit_repayment_micro_grid_prefers_ocr_tokens_when_available():
    out = extract_credit_repayment_records(_credit_page4_lines(), page=4, tokens=_credit_page4_tokens())

    assert out["micro_grid"]["geometry_source"].startswith("ocr_tokens")
    assert out["micro_grid"]["audit"]["source_token_count"] == len(_credit_page4_tokens())
    year_cells = [
        cell
        for row in out["micro_grid"]["cells"]
        for cell in row
        if cell.get("role") == "year"
    ]
    assert year_cells[0]["text"] == "2021"
    assert year_cells[0]["bbox"]
    assert _record_tuples(out["repayment_records"]) == _expected_repayment_tuples()


def test_micro_grid_candidate_detector_is_anchor_gated():
    candidates = detect_micro_grid_candidates(_credit_page4_tokens(), lines=_credit_page4_lines(), page=4)
    assert candidates
    assert "anchor_temporal_record" in candidates[0].reason_codes

    negative = extract_credit_repayment_records(
        [
            {"content": "个人消费贷款", "bbox": [80, 120, 200, 140]},
            {"content": "NN N N", "bbox": [300, 180, 520, 200]},
            {"content": "000 0", "bbox": [300, 210, 520, 230]},
        ],
        page=4,
    )
    assert negative["micro_grid"] is None
    assert negative["repayment_records"] == []


def test_allowlist_normalization_filters_ocr_noise():
    assert normalize_allowlist_text("ＣN.O〇x", {"C", "N", "0"}, max_chars=4) == "N000"
    assert normalize_allowlist_text("O,OOO.50元", set("0123456789.,"), max_chars=16) == "0,000.50"


def test_repayment_mapper_is_credit_plugin_not_core_export():
    import importlib

    import docmirror.ocr.micro_grid as micro_grid

    assert "extract_credit_repayment_records" not in micro_grid.__all__
    assert not hasattr(micro_grid, "extract_credit_repayment_records")
    try:
        importlib.import_module("docmirror.ocr.micro_grid.repayment")
    except ModuleNotFoundError:
        pass
    else:
        raise AssertionError("credit repayment mapper must not live under core.ocr.micro_grid")


def test_cell_crop_ocr_fills_missing_target_cell(monkeypatch):
    lines = [
        {"content": "2020年09月-2021年02月的还款记录", "bbox": [280.46, 194.67, 510.65, 217.78], "confidence": 1.0},
        {"content": "1 122689 113.45710", "bbox": [130.84, 222.65, 733.57, 241.51], "confidence": 1.0},
        {"content": "C", "bbox": [186.90, 249.42, 206.56, 267.06], "confidence": 1.0},
        {"content": "2021", "bbox": [75.71, 262.80, 112.67, 280.44], "confidence": 1.0},
    ]

    class FakeRecognition:
        text = "N"
        confidence = 0.91
        source = "cell_crop_ocr"
        raw_text = "N"
        audit = {"region": (1, 2, 3, 4)}

    def fake_recognize(*args, **kwargs):
        return FakeRecognition()

    class FakeImage:
        shape = (1200, 834, 3)

    monkeypatch.setattr(repayment_mod, "recognize_micro_cell_from_image", fake_recognize)
    out = extract_credit_repayment_records(
        lines,
        page=4,
        page_width=834,
        page_height=1207,
        page_image=FakeImage(),
        enable_cell_ocr=True,
    )

    assert (2021, 1, "N") in [(r["year"], r["month"], r["status"]) for r in out["repayment_records"]]
    assert out["micro_grid"]["audit"]["cell_crop_ocr"]["attempts"] >= 1
    assert out["micro_grid"]["audit"]["cell_crop_ocr"]["hits"] >= 1
    status_cells = [
        cell
        for row in out["micro_grid"]["cells"]
        for cell in row
        if cell["role"] == "status" and cell["col_index"] == 1
    ]
    assert status_cells[0]["recognition_source"] == "cell_crop_ocr"


def test_forensic_api_exports_micro_grids_without_domain_semantics():
    out = extract_credit_repayment_records(_credit_page4_lines(), page=4)
    ds: dict = {"credit_repayment_records": out["repayment_records"]}
    merge_micro_grid_structures_into_bundles(ds, [out["micro_grid"]])
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=ds,
        )
    )

    standard = pr.to_mirror_json_vnext(mirror_level="standard")
    forensic = pr.to_mirror_json_vnext(mirror_level="forensic")

    assert "repayment_records" not in standard
    standard_grid = _micro_grid_structure_from_document(standard)
    standard_cell = next(
        cell
        for row in standard_grid["cells"]
        for cell in row
        if cell.get("role") == "status"
    )
    assert standard_grid["grid_type_hint"] == "credit_repayment_record"
    assert standard_cell["text"] == "N"
    assert standard_cell["bbox"]
    assert "token_ids" not in standard_cell
    assert "audit" not in standard_grid
    forensic_grid = _micro_grid_structure_from_document(forensic)
    assert forensic_grid["grid_type_hint"] == "credit_repayment_record"


def test_credit_plugin_maps_generic_scanned_micro_grid_evidence():
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=_micro_grid_bundle_domain(),
        )
    )
    output = {"data": {}, "document": {}}

    enriched = enrich_credit_report_output(output, parse_result=pr)

    assert [
        (r["year"], r["month"], r["status"], r["overdue_amount"])
        for r in enriched["repayment_records"]
    ] == [
        (2021, 1, "N", "0"),
        (2021, 2, "C", "0"),
        (2020, 9, "N", "0"),
        (2020, 10, "N", "0"),
        (2020, 11, "N", "0"),
        (2020, 12, "N", "0"),
    ]
    ds = pr.entities.domain_specific
    assert ds["credit_repayment_records"]
    assert micro_grid_structures_from_bundles(ds)
    assert "_micro_grids" not in ds


def test_forensic_api_exports_generic_scanned_micro_grid_evidence_only():
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=_micro_grid_bundle_domain(),
        )
    )

    standard = pr.to_mirror_json_vnext(mirror_level="standard")
    forensic = pr.to_mirror_json_vnext(mirror_level="forensic")

    assert "scanned_micro_grid_evidence" not in standard
    forensic_doc = forensic
    assert forensic_doc["scanned_ocr_pages"][0]["page"] == 4
    assert forensic_doc["scanned_ocr_pages"][0]["line_count"] > 0
    assert forensic_doc["scanned_ocr_pages"][0]["token_count"] > 0
    assert forensic_doc["scanned_ocr_pages"][0]["payload"] == "external_evidence_bundle"
    evidence = forensic_doc["scanned_micro_grid_evidence"][0]
    assert evidence["page"] == 4
    assert evidence["ocr_page_ref"] == forensic_doc["scanned_ocr_pages"][0]["ocr_page_id"]
    assert "lines" not in evidence
    assert "tokens" not in evidence


def test_four_file_forensic_mirror_includes_plugin_primed_micro_grids_without_semantics():
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=_micro_grid_bundle_domain(),
        )
    )

    outputs = build_all_projections(pr, mirror_level="forensic")

    document = outputs["mirror"]
    assert "repayment_records" not in document
    grid = _micro_grid_structure_from_document(document)
    assert grid["grid_type_hint"] == "credit_repayment_record"
    assert grid["cells"][0][0]["bbox"]
    page4 = next(p for p in document["pages"] if p.get("page_number") == 4)
    assert any(r.get("kind") == "micro_grid" for r in page4.get("regions") or [])
    assert outputs["community"]["repayment_records"][0]["status"] == "N"


def test_four_file_standard_mirror_includes_compact_plugin_primed_micro_grids():
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=_micro_grid_bundle_domain(),
        )
    )

    outputs = build_all_projections(pr, mirror_level="standard")

    document = outputs["mirror"]
    grid = _micro_grid_structure_from_document(document)
    status_cell = next(
        cell
        for row in grid["cells"]
        for cell in row
        if cell.get("role") == "status"
    )
    assert "repayment_records" not in document
    assert "scanned_micro_grid_evidence" not in document
    page4 = next(p for p in document["pages"] if p.get("page_number") == 4)
    assert page4.get("flow") is not None
    assert any(r.get("kind") == "micro_grid" for r in page4.get("regions") or [])
    assert grid["grid_id"] == "mg_p4_repayment_0"
    assert status_cell["text"] == "N"
    assert status_cell["bbox"]
    assert "token_ids" not in status_cell
    assert outputs["community"]["repayment_records"][0]["status"] == "N"


def test_write_four_files_forensic_mirror_includes_plugin_primed_micro_grids(tmp_path):
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=_micro_grid_bundle_domain(),
        )
    )

    _task_id, written = write_four_files(
        pr,
        tmp_path,
        task_id="task_micro_grid",
        mirror_level="forensic",
    )

    mirror = json.loads(written["mirror"].read_text(encoding="utf-8"))
    document = mirror
    assert "repayment_records" not in document
    grid = _micro_grid_structure_from_document(document)
    assert grid["grid_type_hint"] == "credit_repayment_record"
    assert grid["cells"][0][0]["bbox"]
