import json
import zipfile
from pathlib import Path

from scripts.validate.run_udtr_cross_format_matrix import run_cross_format_matrix
from scripts.validate.validate_udtr_golden import (
    summarize_manifest_file,
    validate_manifest_file,
    validate_mirror_against_expectations,
)


def test_validate_mirror_against_metadata_only_expectations():
    mirror = {
        "pages": [
            {
                "page_id": "page:0010",
                "page_number": 10,
                "coordinate_transform": {"page_normalization": {"selected_rotation": 90}},
            }
        ],
        "mirror": {"schema": "docmirror.mirror_json"},
        "source": {},
        "document": {},
        "evidence": {},
        "regions": [],
        "blocks": [
            {"id": "blk:heading:1", "type": "heading", "text": "所有者权益变动表"},
            {
                "id": "blk:table:1",
                "type": "table",
                "page_ids": ["page:0010"],
                "content": {
                    "statement_structure": {
                        "statement_type": "owners_equity_changes",
                        "rules": [{"type": "roll_forward", "validation": {"status": "pass"}}],
                        "account_rows": [{"row_index": 1}, {"row_index": 2}],
                        "quality": {"requires_review": False},
                    }
                },
            },
        ],
        "graph": {
            "edges": [
                {"metadata": {"relation_kind": "seal_overlays"}},
                {"metadata": {"relation_kind": "derived_from_region_candidate"}},
            ]
        },
        "semantics": {},
        "diagnostics": {
            "pipeline": [
                {
                    "stage": "udtr_profile_summary",
                    "status": "ok",
                    "page_count": 1,
                    "region_count": 0,
                    "block_count": 2,
                    "edge_count": 2,
                    "evidence_atom_counts": {"text": 4},
                    "quality_gate_count": 2,
                    "quality_event_count": 2,
                }
            ]
        },
        "assets": {},
        "quality": {
            "coverage": {"residual_ratio": 0.0},
            "verification": {
                "unit_count": 12,
                "applicable_unit_count": 10,
                "verified_unit_ratio": 1.0,
                "conflict_ratio": 0.0,
                "unit_type_counts": {"table_cell": 8, "text_span": 2},
                "candidate_source_counts": {"table_grid_cell": 8, "evidence_atom_text": 4},
                "claim_type_counts": {"candidate_vote": 12},
                "crop_ocr": {
                    "status": "ok",
                    "processed_count": 2,
                    "agreement_count": 2,
                    "conflict_count": 0,
                },
            },
            "gates": [
                {"id": "gate:page_normalization_confidence", "status": "pass"},
                {"id": "gate:financial_statement_formula", "status": "pass"},
            ],
            "events": [
                {
                    "event_type": "quality_gate",
                    "status": "pass",
                    "severity": "info",
                    "actionable": False,
                    "gate_id": "gate:page_normalization_confidence",
                },
                {
                    "event_type": "quality_gate",
                    "status": "pass",
                    "severity": "info",
                    "actionable": False,
                    "gate_id": "gate:financial_statement_formula",
                },
            ],
            "event_summary": {
                "event_count": 2,
                "actionable_count": 0,
                "by_status": {"pass": 2},
                "by_severity": {"info": 2},
                "actionable_gate_ids": [],
            },
        },
    }

    errors = validate_mirror_against_expectations(
        mirror,
        {
            "canonical_shape": True,
            "page_count": 1,
            "min_table_count": 1,
            "max_residual_ratio": 0.01,
            "required_page_rotations": {"10": 90},
            "required_gates": {
                "gate:page_normalization_confidence": "pass",
                "gate:financial_statement_formula": ["pass", "not_applicable"],
            },
            "required_relation_kinds": {
                "seal_overlays": 1,
                "derived_from_region_candidate": 1,
            },
            "required_statement_structures": [
                {
                    "page_number": 10,
                    "statement_type": "owners_equity_changes",
                    "min_rule_count": 1,
                    "rule_validation_status": "pass",
                    "min_account_rows": 2,
                    "requires_review": False,
                }
            ],
            "verification": {
                "min_unit_count": 12,
                "min_applicable_unit_count": 10,
                "min_verified_unit_ratio": 1.0,
                "max_conflict_ratio": 0.0,
                "required_unit_type_counts": {"table_cell": 8},
                "required_candidate_source_counts": {"evidence_atom_text": 4},
                "required_claim_type_counts": {"candidate_vote": 12},
                "crop_ocr": {
                    "status": "ok",
                    "min_processed_count": 2,
                    "min_agreement_count": 2,
                    "max_conflict_count": 0,
                },
            },
            "quality_events": {
                "summary_matches_events": True,
                "min_event_count": 2,
                "max_actionable_count": 0,
                "required_status_counts": {"pass": 2},
                "required_severity_counts": {"info": 2},
            },
            "profile_summary": {
                "min_page_count": 1,
                "min_block_count": 2,
                "min_quality_gate_count": 2,
                "min_quality_event_count": 2,
                "required_evidence_atom_counts": {"text": 4},
            },
            "required_text_probes": ["所有者权益变动表"],
        },
    )

    assert errors == []


def test_validate_manifest_file_resolves_relative_outputs(tmp_path: Path):
    mirror_path = tmp_path / "mirror.json"
    mirror_path.write_text(
        json.dumps(
            {
                "pages": [{"page_number": 1, "coordinate_transform": {"page_normalization": {"selected_rotation": 0}}}],
                "mirror": {"schema": "docmirror.mirror_json"},
                "source": {},
                "document": {},
                "evidence": {},
                "regions": [],
                "blocks": [{"id": "blk:table:1", "type": "table", "text": "审计报告"}],
                "graph": {"edges": [{"metadata": {"relation_kind": "derived_from_region_candidate"}}]},
                "semantics": {},
                "diagnostics": {},
                "assets": {},
                "quality": {
                    "coverage": {"residual_ratio": 0.0},
                    "gates": [{"id": "gate:coordinate_transform_invertible", "status": "pass"}],
                },
            }
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": "1.0",
                "cases": [
                    {
                        "case_id": "synthetic",
                        "mirror_output": "mirror.json",
                        "expectations": {
                            "canonical_shape": True,
                            "page_count": 1,
                            "min_table_count": 1,
                            "required_gates": {"gate:coordinate_transform_invertible": "pass"},
                            "required_relation_kinds": {"derived_from_region_candidate": 1},
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert validate_manifest_file(manifest_path) == []


def test_validate_manifest_file_checks_cross_case_parity_groups(tmp_path: Path):
    def mirror_payload(filename: str) -> dict:
        return {
            "mirror": {"schema": "docmirror.mirror_json"},
            "source": {"filename": filename},
            "document": {},
            "pages": [{"page_number": 1}],
            "evidence": {},
            "regions": [{"kind": "text"}],
            "blocks": [{"id": "blk:text:1", "type": "paragraph", "text": "hello"}],
            "graph": {"edges": []},
            "semantics": {},
            "quality": {
                "gates": [{"id": "gate:evidence_plane_built", "status": "pass"}],
                "events": [{"status": "pass", "severity": "info", "actionable": False}],
                "event_summary": {
                    "event_count": 1,
                    "actionable_count": 0,
                    "by_status": {"pass": 1},
                    "by_severity": {"info": 1},
                },
            },
            "diagnostics": {
                "pipeline": [
                    {
                        "stage": "udtr_profile_summary",
                        "page_count": 1,
                        "region_count": 1,
                        "block_count": 1,
                        "quality_gate_count": 1,
                        "quality_event_count": 1,
                    }
                ]
            },
            "assets": {},
        }

    (tmp_path / "sample.pdf.json").write_text(json.dumps(mirror_payload("sample.pdf")), encoding="utf-8")
    (tmp_path / "sample.docx.json").write_text(json.dumps(mirror_payload("sample.docx")), encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": "1.0",
                "cases": [
                    {"case_id": "pdf", "mirror_output": "sample.pdf.json", "expectations": {"canonical_shape": True}},
                    {"case_id": "docx", "mirror_output": "sample.docx.json", "expectations": {"canonical_shape": True}},
                ],
                "parity_groups": [
                    {
                        "group_id": "synthetic_cross_format",
                        "case_ids": ["pdf", "docx"],
                        "required_present_count": 2,
                        "compare": [
                            "canonical_shape",
                            "page_count",
                            "block_type_counts",
                            "region_kind_counts",
                            "quality_gate_statuses",
                            "event_summary",
                            "profile_counts",
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert validate_manifest_file(manifest_path) == []
    summary = summarize_manifest_file(manifest_path)
    assert summary["loaded_case_count"] == 2
    assert summary["case_status_counts"] == {"passed": 2}
    assert summary["gate_status_counts"] == {"pass": 2}
    assert summary["quality_event_status_counts"] == {"pass": 2}
    assert summary["profile_totals"]["block_count"] == 2
    assert summary["parity_error_count"] == 0


def test_private_golden_manifest_can_skip_missing_output_by_default(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": "1.0",
                "cases": [
                    {
                        "case_id": "private_missing",
                        "private_source": True,
                        "skip_if_missing": True,
                        "mirror_output": "missing.json",
                        "expectations": {"page_count": 1},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert validate_manifest_file(manifest_path) == []
    strict_errors = validate_manifest_file(manifest_path, allow_missing_private=False)
    assert strict_errors == [f"private_missing: mirror_output not found: {tmp_path / 'missing.json'}"]


def test_run_cross_format_matrix_generates_and_validates_outputs(tmp_path: Path):
    sources = tmp_path / "sources"
    outputs = tmp_path / "outputs"
    sources.mkdir()
    _write_minimal_docx(sources / "sample.docx")
    _write_minimal_xlsx(sources / "sample.xlsx")
    (sources / "sample.html").write_text("<html><body><p>HTML fixture</p></body></html>", encoding="utf-8")
    (sources / "sample.eml").write_text("Subject: Mail fixture\n\nBody fixture", encoding="utf-8")
    with zipfile.ZipFile(sources / "sample.ofd", "w") as zf:
        zf.writestr("Doc_0/Pages/Page_0/Content.xml", "<Page><TextCode>OFD fixture</TextCode></Page>")

    cases = []
    for name in ("docx", "xlsx", "html", "eml", "ofd"):
        filename = f"sample.{name}"
        case_id = f"real_{name}"
        cases.append(
            {
                "case_id": case_id,
                "source_path": f"sources/{filename}",
                "mirror_output": f"outputs/{name}/001_mirror.json",
                "expectations": {
                    "canonical_shape": True,
                    "page_count": 1,
                    "required_gates": {"gate:evidence_plane_built": "pass"},
                    "quality_events": {"summary_matches_events": True, "min_event_count": 1},
                    "profile_summary": {"min_page_count": 1, "min_block_count": 1},
                },
            }
        )
    manifest_path = tmp_path / "cross_format_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": "1.0",
                "cases": cases,
                "parity_groups": [
                    {
                        "group_id": "cross_format_contract",
                        "case_ids": [case["case_id"] for case in cases],
                        "required_present_count": 5,
                        "compare": ["canonical_shape"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = run_cross_format_matrix(manifest_path, allow_missing_private=False)

    assert report["status"] == "ok"
    assert len(report["processed_case_ids"]) == 5
    assert report["summary"]["loaded_case_count"] == 5
    assert (outputs / "docx" / "001_mirror.json").is_file()


def _write_minimal_docx(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "word/document.xml",
            (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>Word fixture</w:t></w:r></w:p></w:body></w:document>"
            ),
        )


def _write_minimal_xlsx(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            (
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Name</t></is></c>'
                '<c r="B1"><v>1</v></c></row></sheetData></worksheet>'
            ),
        )
