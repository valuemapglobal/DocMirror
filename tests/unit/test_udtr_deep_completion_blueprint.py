import pytest

from docmirror.models.entities.parse_result import CellValue, PageContent, ParseResult, TableBlock, TableRow
from docmirror.models.mirror.vnext import BlockInfo, EvidenceAtom, GraphEdge
from docmirror.output.mirror import MirrorCoreVNext
from docmirror.quality.udtr_gates import build_udtr_quality_gates
from docmirror.structure.normalization import build_normalization_trace, estimate_deskew_angle, is_invertible_matrix
from docmirror.structure.region_graph import produce_region_candidates, solve_region_graph
from docmirror.structure.relations import add_udtr_relation_edges
from docmirror.structure.tables.statement import build_statement_structure, extract_note_ref, normalize_note_ref
from docmirror.structure.verification import (
    FunctionVerificationRulePack,
    VerificationRule,
    VerificationRulePackRegistry,
    build_verification_report,
    default_verification_rule_pack_registry,
)


class _Region:
    def __init__(self, id, kind, bbox, evidence_ids, role="body", confidence=0.9):
        self.id = id
        self.page_id = "page:0001"
        self.kind = kind
        self.role = role
        self.bbox = bbox
        self.evidence_ids = evidence_ids
        self.confidence = confidence
        self.diagnostics = {"grouping": "test_detector"}


def test_normalization_trace_is_invertible_for_landscape_rotation():
    trace = build_normalization_trace(
        page_id="page:0010",
        source_width=595.2,
        source_height=841.68,
        source_rotation=0,
        selected_content_rotation=90,
        selected_reason="ocr_orientation_probe",
        confidence=0.95,
    )

    payload = trace.to_dict()

    assert payload["display_width"] == 841.68
    assert payload["display_height"] == 595.2
    assert payload["selected_content_rotation"] == 90
    assert is_invertible_matrix(payload["matrix"]) is True
    assert payload["inverse_matrix"]


def test_deskew_estimator_uses_vector_line_angles_conservatively():
    page = {
        "vector_lines": [
            {"x0": 0, "y0": 10, "x1": 100, "y1": 11.75},
            {"x0": 0, "y0": 30, "x1": 100, "y1": 31.75},
            {"x0": 0, "y0": 50, "x1": 100, "y1": 51.75},
        ]
    }

    angle = estimate_deskew_angle(page)

    assert 0.9 < angle < 1.1


def test_region_graph_solver_explains_ownership_and_overlay():
    regions = [
        _Region("reg:0001:table:0001", "table_like", [0, 0, 100, 100], ["ev:text:1"]),
        _Region("reg:0001:seal:0001", "seal", [10, 10, 40, 40], ["ev:seal:1"], role="seal"),
    ]

    graph = solve_region_graph(
        page_id="page:0001",
        regions=regions,
        all_evidence_ids=["ev:text:1", "ev:seal:1", "ev:unowned:1"],
    )
    diagnostics = graph.to_diagnostics()

    assert diagnostics["candidate_count"] == 2
    assert diagnostics["ownership"]["owned"]["ev:text:1"] == "reg:0001:table:0001"
    assert diagnostics["ownership"]["residual"] == ["ev:unowned:1"]
    assert diagnostics["ownership"]["overlay"]["reg:0001:seal:0001"] == "reg:0001:table:0001"


def test_region_graph_solver_explains_candidate_competition_and_containment():
    regions = [
        _Region("reg:0001:table:0001", "table_like", [0, 0, 100, 100], ["ev:table:1"], confidence=0.9),
        _Region("reg:0001:text:0001", "text", [10, 10, 30, 30], ["ev:text:1"], confidence=0.8),
        _Region("reg:0001:text:0002", "text", [10, 10, 30, 30], ["ev:text:2"], confidence=0.7),
    ]

    graph = solve_region_graph(
        page_id="page:0001",
        regions=regions,
        all_evidence_ids=["ev:table:1", "ev:text:1", "ev:text:2", "ev:missing:1"],
    )
    diagnostics = graph.to_diagnostics()
    by_region = {
        region_id: candidate
        for candidate in diagnostics["candidates"]
        for region_id in [candidate["selected_region_id"], *candidate.get("source_region_ids", [])]
        if region_id
    }

    assert diagnostics["duplicate_candidate_count"] == 1
    assert diagnostics["merged_candidate_count"] == 1
    assert diagnostics["containment_relation_count"] >= 1
    assert by_region["reg:0001:text:0001"]["parent_candidate_ids"] == ["cand:reg:0001:table:0001"]
    assert by_region["reg:0001:text:0002"]["merge_reason"] == "same_kind_high_iou"
    assert by_region["reg:0001:text:0002"]["merged_candidate_ids"] == ["cand:reg:0001:text:0002"]
    assert diagnostics["ownership"]["rejected_candidates"][0]["reason"] == "merged_duplicate_candidate"
    assert diagnostics["residual_explanations"] == [
        {
            "evidence_id": "ev:missing:1",
            "reason": "no_detector_candidate_claim",
            "candidate_count": 0,
            "detector_reason": "evidence_atom_missing_from_index",
        }
    ]


def test_region_graph_residual_explains_unselected_candidate_claim():
    from docmirror.structure.region_graph.models import RegionCandidate

    graph = solve_region_graph(
        page_id="page:0001",
        regions=[],
        all_evidence_ids=["ev:candidate:1"],
        candidates=[
            RegionCandidate(
                candidate_id="cand:test",
                page_id="page:0001",
                kind="text",
                bbox=[0, 0, 10, 10],
                evidence_ids=["ev:candidate:1"],
                confidence=0.5,
                selected_region_id="reg:missing",
            )
        ],
    )

    assert graph.to_diagnostics()["residual_explanations"] == [
        {
            "evidence_id": "ev:candidate:1",
            "reason": "candidate_not_selected",
            "candidate_ids": ["cand:test"],
            "candidate_count": 1,
            "candidate_kinds": ["text"],
            "candidate_detectors": [],
            "candidate_producer_ids": [],
            "detector_reason": "candidate_claim_exists_but_no_selected_region_ownership",
        }
    ]


def test_region_graph_residual_explains_no_candidate_by_atom_kind():
    atom = EvidenceAtom(
        id="ev:table:orphan",
        kind="text_token",
        source_kind="xlsx_cell",
        page_id="page:0001",
        text="42",
        bbox=[10, 10, 20, 20],
        metadata={"block_type": "table"},
    )

    graph = solve_region_graph(
        page_id="page:0001",
        regions=[],
        all_evidence_ids=["ev:table:orphan"],
        evidence_by_id={atom.id: atom},
    )

    assert graph.to_diagnostics()["residual_explanations"] == [
        {
            "evidence_id": "ev:table:orphan",
            "reason": "no_detector_candidate_claim",
            "candidate_count": 0,
            "detector_reason": "table_detector_skipped_or_rejected_text_atom",
            "atom": {
                "kind": "text_token",
                "source_kind": "xlsx_cell",
                "has_bbox": True,
                "block_type": "table",
                "role": "",
            },
        }
    ]


def test_region_graph_candidate_producer_is_detector_first_boundary():
    regions = [
        _Region("reg:0001:table:0001", "table_like", [0, 0, 100, 100], ["ev:table:1"], confidence=0.9),
        _Region("reg:0001:table:0002", "table_like", [1, 1, 101, 101], ["ev:table:2"], confidence=0.8),
    ]

    batch = produce_region_candidates(page_id="page:0001", regions=regions)
    graph = solve_region_graph(
        page_id="page:0001",
        regions=regions,
        all_evidence_ids=["ev:table:1", "ev:table:2"],
        candidates=batch.candidates,
    )
    diagnostics = graph.to_diagnostics()
    merged = diagnostics["candidates"][0]

    assert diagnostics["candidate_count_before_merge"] == 2
    assert diagnostics["candidate_count_after_merge"] == 1
    assert diagnostics["merged_candidate_count"] == 1
    assert batch.diagnostics["candidate_producer_count"] == 4
    assert batch.diagnostics["candidate_producer_counts"]["table_region_candidate_producer"] == 2
    assert merged["features"]["producer_id"] == "table_region_candidate_producer"
    assert set(merged["source_region_ids"]) == {"reg:0001:table:0001", "reg:0001:table:0002"}


def test_reconstructor_registry_can_return_structured_report():
    from docmirror.structure.reconstructors import ReconstructionContext, RegionReconstructorRegistry

    region = _Region("reg:0001:unknown:0001", "unknown", [0, 0, 50, 20], [], role="unknown")
    context = ReconstructionContext(evidence_plane=None, atom_by_id={}, atom_text={})

    report = RegionReconstructorRegistry().reconstruct_with_report(region, context)

    assert report.block.type == "residual"
    assert report.selected_reconstructor == "minimal_residual_reconstructor"
    assert report.contract["id"] == "minimal_residual_reconstructor"
    assert report.to_dict()["block_id"] == report.block.id
    assert report.block.provenance["dispatch"]["selected_reconstructor"] == report.selected_reconstructor


def test_financial_statement_structure_preserves_grid_and_adds_semantics():
    block = type("Block", (), {})()
    block.content = {
        "grid": {
            "columns": [
                {"id": "c0", "index": 0, "header": "项目"},
                {"id": "c1", "index": 1, "header": "实收资本"},
                {"id": "c2", "index": 2, "header": "资本公积"},
                {"id": "c3", "index": 3, "header": "所有者权益合计"},
            ],
            "rows": [
                {"index": 0, "role": "header"},
                {"index": 1, "role": "data"},
                {"index": 2, "role": "data"},
                {"index": 3, "role": "data"},
            ],
            "cells": [
                {"row": 1, "col": 0, "text": "二、本年年初余额"},
                {"row": 1, "col": 1, "text": "附注五"},
                {"row": 2, "col": 0, "text": "三、本期增减变动金额"},
                {"row": 3, "col": 0, "text": "四、本年年末余额"},
            ],
        }
    }

    structure = build_statement_structure(
        block,
        source_text="所有者权益变动表 归属于母公司所有者权益 实收资本 资本公积 所有者权益合计",
    )

    assert structure["statement_type"] == "owners_equity_changes"
    assert structure["header_bands"]
    assert structure["column_groups"][0]["label"] == "归属于母公司所有者权益"
    assert {row["role"] for row in structure["account_rows"]} >= {
        "current_year_opening_balance",
        "current_period_change",
        "current_year_ending_balance",
    }
    assert structure["account_rows"][0]["note_ref"] == "附注五"
    assert structure["rules"][0]["type"] == "roll_forward"


def test_financial_statement_kernels_capture_hierarchy_and_formula_validation():
    block = type("Block", (), {})()
    block.content = {
        "grid": {
            "columns": [
                {"id": "c0", "index": 0, "header": "项目"},
                {"id": "c1", "index": 1, "header": "实收资本"},
                {"id": "c2", "index": 2, "header": "资本公积"},
                {"id": "c3", "index": 3, "header": "所有者权益合计"},
            ],
            "rows": [
                {"index": 0, "role": "header"},
                {"index": 1, "role": "data"},
                {"index": 2, "role": "data"},
                {"index": 3, "role": "data"},
                {"index": 4, "role": "data"},
            ],
            "cells": [
                {"row": 0, "col": 1, "text": "归属于母公司所有者权益", "col_span": 2},
                {"row": 1, "col": 0, "text": "二、本年年初余额"},
                {"row": 1, "col": 1, "text": "100.00"},
                {"row": 2, "col": 0, "text": "（一）本期投入资本"},
                {"row": 2, "col": 1, "text": "20.00"},
                {"row": 3, "col": 0, "text": "三、本期增减变动金额"},
                {"row": 3, "col": 1, "text": "20.00"},
                {"row": 4, "col": 0, "text": "四、本年年末余额"},
                {"row": 4, "col": 1, "text": "120.00"},
            ],
        }
    }

    structure = build_statement_structure(block, source_text="所有者权益变动表")
    rule = structure["rules"][0]

    assert structure["header_bands"][0]["cells"][0]["is_merged"] is True
    assert structure["column_groups"][0]["source"] == "merged_header_band"
    assert structure["account_rows"][1]["parent_row_index"] == 1
    assert structure["account_rows"][1]["path"] == ["本年年初余额", "本期投入资本"]
    assert rule["validation"]["status"] == "pass"
    assert rule["validation"]["comparisons"][0]["expected"] == 120.0


def test_financial_statement_formula_validation_skips_ambiguous_role_rows():
    block = type("Block", (), {})()
    block.content = {
        "grid": {
            "columns": [
                {"id": "c0", "index": 0, "header": "项目"},
                {"id": "c1", "index": 1, "header": "所有者权益合计"},
            ],
            "rows": [
                {"index": 0, "role": "header"},
                {"index": 1, "role": "data"},
                {"index": 2, "role": "data"},
            ],
            "cells": [
                {"row": 1, "col": 0, "text": "三、本期增减变动金额（减少以“一”二、本年年初余额"},
                {"row": 1, "col": 1, "text": "250,000,000.00"},
                {"row": 2, "col": 0, "text": "四、本年年末余额"},
                {"row": 2, "col": 1, "text": "250,000,000.00"},
            ],
        }
    }

    structure = build_statement_structure(block, source_text="所有者权益变动表")

    assert structure["rules"][0]["type"] == "roll_forward"
    assert structure["rules"][0]["validation"] == {"status": "not_evaluated", "reason": "ambiguous_role_rows"}
    assert structure["quality"]["requires_review"] is False


def test_statement_note_refs_require_explicit_note_context_for_bare_values():
    assert normalize_note_ref("附注五") == "附注五"
    assert normalize_note_ref("五") is None
    assert extract_note_ref([{"text": "五"}, {"text": "100.00"}], "货币资金") is None
    assert extract_note_ref([{"text": "附注"}, {"text": "五"}], "货币资金") == "附注五"


def test_mirror_core_outputs_contracts_normalization_gates_and_statement_structure():
    table = TableBlock(
        table_id="pt_10_0",
        headers=["项目", "实收资本", "资本公积", "所有者权益合计"],
        page=10,
        bbox=[42.5, 117.0, 803.0, 554.0],
        extraction_layer="scanned_ocr_statement_grid",
        extraction_confidence=0.93,
        metadata={
            "role": "financial_statement",
            "statement_keywords": ["所有者权益变动表"],
            "ocr_rotation": 90,
            "ocr_orientation_score": 128.5,
            "text_chars": 320,
            "cjk_ratio": 0.82,
            "keyword_hits": 3,
            "numeric_tokens": 18,
            "garbage_tokens": 0,
            "normalized_page_width": 842.0,
            "normalized_page_height": 595.0,
            "geometry": {
                "geometry_source": "scanned_ocr_statement_grid",
                "geometry_confidence": 0.93,
            },
        },
        rows=[
            TableRow(cells=[CellValue(text="二、本年年初余额"), CellValue(text="250,000,000.00")]),
            TableRow(cells=[CellValue(text="三、本期增减变动金额"), CellValue(text="96,657,505.50")]),
            TableRow(cells=[CellValue(text="四、本年年末余额"), CellValue(text="346,657,505.50")]),
        ],
    )
    result = ParseResult(pages=[PageContent(page_number=10, width=842, height=595, tables=[table])])

    payload = MirrorCoreVNext().process(result).to_dict()

    page = payload["pages"][0]
    assert page["coordinate_transform"]["content_rotation_applied"] == 90
    assert page["coordinate_transform"]["inverse_matrix"]
    signals = page["coordinate_transform"]["page_normalization"]["comparison_signals"]
    assert signals["ocr_rotation"] == 90
    assert signals["keyword_hits"] == 3
    assert signals["numeric_tokens"] == 18

    table_block = next(block for block in payload["blocks"] if block["type"] == "table")
    assert table_block["provenance"]["reconstruction_contract"]["id"] == "financial_statement_reconstructor"
    assert "dispatch" in table_block["provenance"]
    assert table_block["content"]["statement_structure"]["statement_type"] == "owners_equity_changes"
    assert payload["quality"]["event_summary"]["event_count"] == len(payload["quality"]["events"])

    gate_ids = {gate["id"] for gate in payload["quality"]["gates"]}
    assert "gate:page_normalization_confidence" in gate_ids
    assert "gate:coordinate_transform_invertible" in gate_ids
    assert "gate:region_candidate_resolution" in gate_ids
    assert "gate:ownership_explainability" in gate_ids
    assert "gate:overlay_relationship_consistency" in gate_ids
    assert "gate:financial_header_hierarchy" in gate_ids
    assert "gate:financial_statement_formula" in gate_ids
    assert "gate:statement_note_reference" in gate_ids
    assert "gate:visual_artifact_coverage" in gate_ids
    assert "gate:cross_format_projection_consistency" in gate_ids
    assert "gate:verification_unit_coverage" in gate_ids
    assert "gate:verification_value_confidence" in gate_ids
    assert "verification" in payload["quality"]
    assert payload["quality"]["verification"]["unit_count"] > 0


def test_financial_statement_continuation_uses_region_statement_keywords():
    table = TableBlock(
        table_id="pt_11_0",
        headers=["项目", "本期金额", "上期金额"],
        page=11,
        bbox=[42.5, 117.0, 803.0, 554.0],
        extraction_layer="scanned_ocr_statement_grid",
        extraction_confidence=0.91,
        metadata={
            "role": "financial_statement",
            "statement_keywords": ["所有者权益变动表"],
            "ocr_rotation": 90,
            "ocr_orientation_score": 126.0,
            "normalized_page_width": 842.0,
            "normalized_page_height": 595.0,
        },
        rows=[
            TableRow(cells=[CellValue(text="二、本年年初余额"), CellValue(text="250,000,000.00")]),
            TableRow(cells=[CellValue(text="三、本期增减变动金额"), CellValue(text="96,657,505.50")]),
            TableRow(cells=[CellValue(text="四、本年年末余额"), CellValue(text="346,657,505.50")]),
        ],
    )
    result = ParseResult(pages=[PageContent(page_number=11, width=842, height=595, tables=[table])])

    payload = MirrorCoreVNext().process(result).to_dict()

    table_block = next(block for block in payload["blocks"] if block["type"] == "table")
    statement = table_block["content"]["statement_structure"]
    assert table_block["content"]["financial_statement"]["fs_type"] == "所有者权益变动表"
    assert statement["statement_type"] == "owners_equity_changes"
    assert table_block["provenance"]["ocr_rotation"] == 90


def test_udtr_quality_gates_are_not_applicable_without_financial_tables():
    page = type("Page", (), {"page_id": "page:0001", "coordinate_transform": {"matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}})()

    gates = build_udtr_quality_gates(pages=[page], regions=[], blocks=[])
    by_id = {gate["id"]: gate for gate in gates}

    assert by_id["gate:coordinate_transform_invertible"]["status"] == "pass"
    assert by_id["gate:financial_header_hierarchy"]["status"] == "not_applicable"


def test_udtr_quality_gates_cover_overlay_and_formula_rules():
    region = type(
        "Region",
        (),
        {
            "id": "reg:0001:seal:0001",
            "kind": "seal",
            "role": "seal",
            "quality": {"ownership_relation": "overlay", "overlay_target_region_id": "reg:0001:table:0001"},
        },
    )()
    block = type(
        "Block",
        (),
        {
            "id": "blk:table:0001",
            "type": "table",
            "role": "financial_statement",
            "page_ids": ["page:0001"],
            "content": {
                "statement_structure": {
                    "statement_type": "owners_equity_changes",
                    "rules": [{"type": "roll_forward"}],
                    "quality": {"header_hierarchy_confidence": 0.9},
                    "account_rows": [],
                }
            },
        },
    )()

    gates = build_udtr_quality_gates(pages=[], regions=[region], blocks=[block])
    by_id = {gate["id"]: gate for gate in gates}

    assert by_id["gate:overlay_relationship_consistency"]["status"] == "pass"
    assert by_id["gate:financial_statement_formula"]["status"] == "pass"
    assert by_id["gate:statement_note_reference"]["status"] == "not_applicable"


def test_udtr_formula_gate_warns_on_failed_rule_validation():
    block = type(
        "Block",
        (),
        {
            "id": "blk:table:bad_formula",
            "type": "table",
            "role": "financial_statement",
            "page_ids": ["page:0001"],
            "content": {
                "statement_structure": {
                    "statement_type": "owners_equity_changes",
                    "rules": [{"type": "roll_forward", "validation": {"status": "warn"}}],
                    "quality": {"header_hierarchy_confidence": 0.9},
                    "account_rows": [],
                }
            },
        },
    )()

    gates = build_udtr_quality_gates(pages=[], regions=[], blocks=[block])
    formula_gate = {gate["id"]: gate for gate in gates}["gate:financial_statement_formula"]

    assert formula_gate["status"] == "warn"
    assert formula_gate["target_ids"] == ["blk:table:bad_formula"]


def test_universal_verification_report_covers_table_text_kv_and_visual_units():
    table = BlockInfo(
        id="blk:table:verify",
        type="table",
        role="table",
        page_ids=["page:0001"],
        region_ids=["reg:table"],
        bbox=[0, 0, 100, 100],
        evidence_ids=["ev:table"],
        content={
            "grid": {
                "cells": [
                    {"id": "cell:1", "row": 0, "col": 0, "text": "项目", "bbox": [0, 0, 50, 20], "evidence_ids": ["ev:c1"]},
                    {"id": "cell:2", "row": 1, "col": 0, "text": "100.00", "bbox": [0, 20, 50, 40], "evidence_ids": ["ev:c2"]},
                ]
            }
        },
    )
    text = BlockInfo(
        id="blk:paragraph:verify",
        type="paragraph",
        role="body",
        page_ids=["page:0001"],
        bbox=[0, 110, 100, 130],
        text="审计意见",
        evidence_ids=["ev:text"],
    )
    kv = BlockInfo(
        id="blk:kv:verify",
        type="key_value_group",
        role="document_metadata",
        page_ids=["page:0001"],
        bbox=[0, 140, 100, 180],
        content={"fields": [{"key": "公司名称", "value": "杭州华英新塘", "evidence_ids": ["ev:kv"]}]},
    )
    visual = BlockInfo(
        id="blk:artifact:seal:verify",
        type="artifact",
        role="seal",
        page_ids=["page:0001"],
        bbox=[10, 10, 40, 40],
        evidence_ids=["ev:seal"],
    )

    report = build_verification_report(blocks=[table, text, kv, visual])
    summary = report.summary()
    by_type = summary["unit_type_counts"]

    assert by_type["table_cell"] == 2
    assert by_type["text_span"] == 1
    assert by_type["kv_field"] == 1
    assert by_type["visual_object"] == 1
    assert summary["rule_status_counts"]["pass"] >= 1
    assert "coverage" in {rule.rule_type for rule in report.rules}
    assert summary["conflict_ratio"] == 0.0


def test_universal_verification_backfills_missing_evidence_from_spatial_atoms():
    table = BlockInfo(
        id="blk:table:spatial_verify",
        type="table",
        role="table",
        page_ids=["page:0001"],
        region_ids=["reg:table"],
        bbox=[0, 0, 100, 60],
        content={
            "grid": {
                "cells": [
                    {"id": "cell:1", "row": 0, "col": 0, "text": "100.00", "bbox": [0, 0, 50, 20]},
                    {"id": "cell:2", "row": 0, "col": 1, "text": "备注", "bbox": [50, 0, 100, 20]},
                ]
            }
        },
    )
    atom = EvidenceAtom(
        id="ev:inside:amount",
        kind="text_token",
        source_kind="ocr",
        page_id="page:0001",
        text="100.00",
        bbox=[8, 4, 32, 14],
        confidence=0.93,
    )

    report = build_verification_report(blocks=[table], evidence_atoms=[atom])
    amount_unit = next(unit for unit in report.units if unit.selected_value == "100.00")

    assert amount_unit.status == "verified"
    assert amount_unit.evidence_ids == ["ev:inside:amount"]
    assert any(candidate.source == "spatial_evidence_backfill" for candidate in amount_unit.candidates)
    assert any(
        claim.claim_type == "candidate_vote" and claim.status == "verified"
        for claim in report.claims
        if claim.subject_unit_id == amount_unit.unit_id
    )


def test_universal_verification_flags_cross_source_value_conflicts():
    table = BlockInfo(
        id="blk:table:conflict_verify",
        type="table",
        role="table",
        page_ids=["page:0001"],
        region_ids=["reg:table"],
        bbox=[0, 0, 100, 40],
        content={
            "grid": {
                "cells": [
                    {"id": "cell:1", "row": 0, "col": 0, "text": "100.00", "bbox": [0, 0, 50, 20]},
                ]
            }
        },
    )
    atom = EvidenceAtom(
        id="ev:inside:conflict",
        kind="text_token",
        source_kind="ocr",
        page_id="page:0001",
        text="101.00",
        bbox=[8, 4, 32, 14],
        confidence=0.96,
    )

    report = build_verification_report(blocks=[table], evidence_atoms=[atom])
    unit = report.units[0]
    vote_claim = next(claim for claim in report.claims if claim.claim_type == "candidate_vote")

    assert unit.status == "conflict"
    assert vote_claim.status == "conflict"
    assert vote_claim.reasons == ["candidate_value_conflict"]


def test_universal_verification_treats_empty_table_cells_as_not_applicable():
    table = BlockInfo(
        id="blk:table:empty_verify",
        type="table",
        role="table",
        page_ids=["page:0001"],
        region_ids=["reg:table"],
        bbox=[0, 0, 100, 40],
        content={
            "grid": {
                "cells": [
                    {
                        "id": "cell:1",
                        "row": 0,
                        "col": 0,
                        "text": "项目",
                        "bbox": [0, 0, 50, 20],
                        "evidence_ids": ["ev:label"],
                    },
                    {"id": "cell:2", "row": 0, "col": 1, "text": "", "bbox": [50, 0, 100, 20]},
                ]
            }
        },
    )

    report = build_verification_report(blocks=[table])
    summary = report.summary()
    empty_unit = next(unit for unit in report.units if unit.selected_value == "")

    assert empty_unit.status == "not_applicable"
    assert empty_unit.reasons == ["empty_cell"]
    assert summary["unit_status_counts"]["not_applicable"] == 1
    assert summary["applicable_unit_count"] == 1
    assert summary["verified_unit_ratio"] == 1.0


def test_universal_verification_rule_pack_registry_adds_domain_rules():
    table = BlockInfo(
        id="blk:table:rule_pack",
        type="table",
        role="bank_statement",
        page_ids=["page:0001"],
        region_ids=["reg:table"],
        bbox=[0, 0, 100, 40],
        content={
            "grid": {
                "cells": [
                    {"id": "cell:1", "row": 0, "col": 0, "text": "余额", "bbox": [0, 0, 50, 20], "evidence_ids": ["ev:balance"]},
                ]
            }
        },
    )

    def _bank_balance_pack(block: BlockInfo, units):
        if block.role != "bank_statement":
            return []
        return [
            VerificationRule(
                rule_id="rule:test:bank_balance_pack",
                rule_type="bank_statement.balance_continuity",
                status="not_evaluated",
                input_unit_ids=[unit.unit_id for unit in units],
                reason="insufficient_sequence_for_balance_check",
            )
        ]

    registry = default_verification_rule_pack_registry().register(
        FunctionVerificationRulePack("bank_balance_test", _bank_balance_pack)
    )

    report = build_verification_report(blocks=[table], rule_pack_registry=registry)
    rule_types = {rule.rule_type for rule in report.rules}

    assert "coverage" in rule_types
    assert "bank_statement.balance_continuity" in rule_types
    assert "generic_unit_evidence_assignment" in registry.pack_ids()
    assert "statement_structure_rule_bridge" in registry.pack_ids()
    assert "bank_balance_test" in registry.pack_ids()


def test_statement_structure_rules_bridge_into_universal_verification():
    table = BlockInfo(
        id="blk:table:statement_rule_bridge",
        type="table",
        role="financial_statement",
        page_ids=["page:0001"],
        region_ids=["reg:table"],
        bbox=[0, 0, 100, 40],
        content={
            "grid": {
                "cells": [
                    {"id": "cell:1", "row": 0, "col": 0, "text": "四、本年年末余额", "bbox": [0, 0, 50, 20], "evidence_ids": ["ev:ending"]},
                    {"id": "cell:2", "row": 0, "col": 1, "text": "120.00", "bbox": [50, 0, 100, 20], "evidence_ids": ["ev:amount"]},
                ]
            },
            "statement_structure": {
                "statement_type": "owners_equity_changes",
                "rules": [
                    {
                        "type": "roll_forward",
                        "validation": {"status": "pass"},
                    }
                ],
            },
        },
    )

    report = build_verification_report(blocks=[table])

    bridged = [rule for rule in report.rules if rule.rule_id.endswith("statement_structure:0001")]
    assert len(bridged) == 1
    assert bridged[0].rule_type == "roll_forward"
    assert bridged[0].status == "pass"


def test_verification_crop_assets_generate_pngs_for_sample_units(tmp_path):
    fitz = pytest.importorskip("fitz")
    pdf_path = tmp_path / "unit_crop_source.pdf"
    doc = fitz.open()
    page = doc.new_page(width=200, height=100)
    page.insert_text((12, 25), "100.00")
    doc.save(str(pdf_path))
    doc.close()
    mirror = {
        "pages": [
            {
                "page_id": "page:0001",
                "page_number": 1,
                "coordinate_transform": {
                    "inverse_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                },
            }
        ],
        "quality": {
            "verification": {
                "units": [
                    {
                        "unit_id": "unit:test:cell:0000:0000",
                        "unit_type": "table_cell",
                        "block_id": "blk:table:test",
                        "page_ids": ["page:0001"],
                        "bbox": [8, 8, 70, 34],
                        "evidence_ids": ["ev:test"],
                        "selected_value": "100.00",
                    }
                ]
            }
        },
        "diagnostics": {"pipeline": []},
        "assets": {"items": []},
    }
    from docmirror.structure.verification.crops import attach_verification_crop_assets

    assets = attach_verification_crop_assets(mirror, pdf_path=pdf_path, task_dir=tmp_path / "task", max_crops=1)

    assert len(assets) == 1
    asset = assets[0]
    assert asset["kind"] == "verification_unit_crop"
    assert asset["unit_id"] == "unit:test:cell:0000:0000"
    assert (tmp_path / "task" / asset["path"]).is_file()
    assert mirror["quality"]["verification"]["crop_artifact_count"] == 1
    assert mirror["assets"]["items"][0]["path"] == asset["path"]
    assert any(entry["stage"] == "verification_crop_artifacts" and entry["status"] == "ok" for entry in mirror["diagnostics"]["pipeline"])


def test_unit_crop_ocr_candidates_attach_to_verification_units(tmp_path):
    crop_dir = tmp_path / "task" / "assets" / "verification_crops"
    crop_dir.mkdir(parents=True)
    (crop_dir / "crop.png").write_bytes(b"fake-png")
    mirror = {
        "quality": {
            "verification": {
                "units": [
                    {
                        "unit_id": "unit:test:cell:0000:0000",
                        "unit_type": "table_cell",
                        "block_id": "blk:table:test",
                        "page_ids": ["page:0001"],
                        "bbox": [8, 8, 70, 34],
                        "evidence_ids": ["ev:test"],
                        "selected_value": "100.00",
                        "candidates": [{"source": "table_grid_cell", "value": "100.00", "confidence": 1.0, "evidence_ids": ["ev:test"]}],
                    }
                ],
                "claims": [],
            }
        },
        "diagnostics": {"pipeline": []},
        "assets": {
            "items": [
                {
                    "id": "asset:verification_crop:000001",
                    "kind": "verification_unit_crop",
                    "path": "assets/verification_crops/crop.png",
                    "unit_id": "unit:test:cell:0000:0000",
                }
            ]
        },
    }
    from docmirror.structure.verification.crops import attach_unit_crop_ocr_candidates

    summary = attach_unit_crop_ocr_candidates(
        mirror,
        task_dir=tmp_path / "task",
        ocr_runner=lambda _path, _asset: {"engine": "fake_ocr", "text": "100.00", "confidence": 0.93},
    )

    unit = mirror["quality"]["verification"]["units"][0]
    assert summary["candidate_count"] == 1
    assert summary["agreement_count"] == 1
    assert any(candidate["source"] == "unit_crop_ocr" for candidate in unit["candidates"])
    assert mirror["assets"]["items"][0]["ocr"]["status"] == "verified"
    assert any(gate["id"] == "gate:verification_crop_ocr" and gate["status"] == "pass" for gate in mirror["quality"]["gates"])
    assert any(claim["claim_type"] == "unit_crop_ocr_vote" and claim["status"] == "verified" for claim in mirror["quality"]["verification"]["claims"])


def test_unit_crop_ocr_mismatch_requires_review_without_mutating_value(tmp_path):
    crop_dir = tmp_path / "task" / "assets" / "verification_crops"
    crop_dir.mkdir(parents=True)
    (crop_dir / "crop.png").write_bytes(b"fake-png")
    mirror = {
        "quality": {
            "verification": {
                "units": [
                    {
                        "unit_id": "unit:test:cell:0000:0000",
                        "unit_type": "table_cell",
                        "selected_value": "100.00",
                        "evidence_ids": ["ev:test"],
                        "candidates": [],
                    }
                ],
                "claims": [],
            }
        },
        "diagnostics": {"pipeline": []},
        "assets": {
            "items": [
                {
                    "id": "asset:verification_crop:000001",
                    "kind": "verification_unit_crop",
                    "path": "assets/verification_crops/crop.png",
                    "unit_id": "unit:test:cell:0000:0000",
                }
            ]
        },
    }
    from docmirror.structure.verification.crops import attach_unit_crop_ocr_candidates

    summary = attach_unit_crop_ocr_candidates(
        mirror,
        task_dir=tmp_path / "task",
        ocr_runner=lambda _path, _asset: {"engine": "fake_ocr", "text": "101.00", "confidence": 0.95},
    )

    unit = mirror["quality"]["verification"]["units"][0]
    assert unit["selected_value"] == "100.00"
    assert summary["conflict_count"] == 1
    assert mirror["assets"]["items"][0]["ocr"]["status"] == "requires_review"
    assert any(gate["id"] == "gate:verification_crop_ocr" and gate["status"] == "pass" for gate in mirror["quality"]["gates"])


def test_unit_crop_ocr_accepts_reordered_long_number_fragments(tmp_path):
    crop_dir = tmp_path / "task" / "assets" / "verification_crops"
    crop_dir.mkdir(parents=True)
    (crop_dir / "crop.png").write_bytes(b"fake-png")
    mirror = {
        "quality": {
            "verification": {
                "units": [
                    {
                        "unit_id": "unit:test:cell:0000:0000",
                        "unit_type": "table_cell",
                        "selected_value": "415024578.41",
                        "evidence_ids": ["ev:test"],
                        "candidates": [],
                    }
                ],
                "claims": [],
            }
        },
        "diagnostics": {"pipeline": []},
        "assets": {
            "items": [
                {
                    "id": "asset:verification_crop:000001",
                    "kind": "verification_unit_crop",
                    "path": "assets/verification_crops/crop.png",
                    "unit_id": "unit:test:cell:0000:0000",
                }
            ]
        },
    }
    from docmirror.structure.verification.crops import attach_unit_crop_ocr_candidates

    summary = attach_unit_crop_ocr_candidates(
        mirror,
        task_dir=tmp_path / "task",
        ocr_runner=lambda _path, _asset: {"engine": "fake_ocr", "text": "5,024,578.41 415,", "confidence": 0.95},
    )

    assert summary["agreement_count"] == 1
    assert summary["conflict_count"] == 0
    assert mirror["assets"]["items"][0]["ocr"]["status"] == "verified"


def test_relation_builder_adds_visual_and_financial_statement_edges():
    table = BlockInfo(
        id="blk:table:0001",
        type="table",
        role="financial_statement",
        page_ids=["page:0001"],
        region_ids=["reg:0001:table:0001"],
        bbox=[0, 20, 100, 100],
        evidence_ids=["ev:table:1"],
        content={
            "statement_structure": {
                "statement_type": "owners_equity_changes",
                "account_rows": [{"row_index": 1, "label": "货币资金", "note_ref": "附注五"}],
            }
        },
    )
    heading = BlockInfo(
        id="blk:heading:0001",
        type="heading",
        role="h2",
        page_ids=["page:0001"],
        bbox=[0, 0, 100, 10],
        text="所有者权益变动表",
    )
    seal = BlockInfo(
        id="blk:artifact:seal:0001",
        type="artifact",
        role="seal",
        page_ids=["page:0001"],
        bbox=[10, 30, 40, 60],
        evidence_ids=["ev:seal:1"],
    )
    note = BlockInfo(
        id="blk:paragraph:note:0001",
        type="paragraph",
        role="body",
        page_ids=["page:0001"],
        bbox=[0, 110, 100, 130],
        text="附注五 货币资金",
    )
    edges: list[GraphEdge] = []
    counter = {"value": 0}

    def next_edge() -> str:
        counter["value"] += 1
        return f"edge:{counter['value']:06d}"

    add_udtr_relation_edges([heading, table, seal, note], edges, next_edge=next_edge)
    relation_kinds = {edge.metadata.get("relation_kind") for edge in edges}

    assert "seal_overlays" in relation_kinds
    assert "statement_part_of" in relation_kinds
    assert "note_refers_to_account" in relation_kinds
    assert "derived_from_region_candidate" in relation_kinds
