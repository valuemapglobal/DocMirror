# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mirror geometry conservation contract tests."""

from __future__ import annotations

import json
from pathlib import Path

from docmirror.eval.tqg.geometry_oracles import run_mirror_geometry_oracle
from docmirror.input.canonical import assemble_parse_result
from docmirror.models.entities.domain import Block, PageLayout

_CORE_MIRROR_GOLDEN = Path(__file__).resolve().parent / "data" / "synthetic_geometry_golden.json"


def test_canonical_assembler_projects_table_geometry_attrs_to_forensic_cells():
    geometry = {
        "coordinate_system": "pdf_points_top_left",
        "cell_bboxes": [
            [[0, 0, 50, 20], [50, 0, 100, 20]],
            [[0, 20, 50, 40], [50, 20, 100, 40]],
        ],
        "cell_geometry_status": [["exact", "exact"], ["exact", "estimated"]],
        "cell_geometry_loss_reason": [[None, None], [None, "estimated_from_row_col_bands"]],
        "cell_evidence_ids": [[["h0"], ["h1"]], [["c0"], ["c1"]]],
        "cell_token_ids": [[["th0"], ["th1"]], [["tc0"], ["tc1"]]],
        "cell_confidences": [[0.95, 0.94], [0.93, 0.61]],
        "row_bands": [
            {"index": 0, "bbox": [0, 0, 100, 20], "role": "header"},
            {"index": 1, "bbox": [0, 20, 100, 40], "role": "data"},
        ],
        "col_bands": [
            {"index": 0, "bbox": [0, 0, 50, 40]},
            {"index": 1, "bbox": [50, 0, 100, 40]},
        ],
        "geometry_source": "unit",
        "geometry_confidence": 0.9,
    }
    block = Block(
        block_type="table",
        raw_content=[["A", "B"], ["1", ""]],
        bbox=(0, 0, 100, 40),
        page=1,
        attrs={"geometry": geometry, "extraction_layer": "unit", "extraction_confidence": 0.9},
    )
    result = assemble_parse_result((PageLayout(page_number=1, width=100, height=40, blocks=(block,)),), {}, "")
    api = result.to_mirror_json_vnext(mirror_level="forensic")
    table = api["pages"][0]["tables"][0]
    cell = table["rows"][0]["cells"][0]

    assert cell["bbox"] == [0, 20, 50, 40]
    assert cell["row_index"] == 0
    assert cell["col_index"] == 0
    assert cell["geometry_status"] == "exact"
    assert "geometry_loss_reason" not in cell
    assert cell["evidence_ids"] == ["c0"]
    assert cell["token_ids"] == ["tc0"]
    assert cell["geometry_confidence"] == 0.93
    estimated = table["rows"][0]["cells"][1]
    assert estimated["geometry_status"] == "estimated"
    assert estimated["geometry_loss_reason"] == "estimated_from_row_col_bands"
    assert estimated["token_ids"] == ["tc1"]
    assert estimated["geometry_confidence"] == 0.61
    assert table["metadata"]["geometry"]["row_bands"][0]["role"] == "header"


def test_mirror_geometry_oracle_accepts_synthetic_geometry():
    from docmirror.eval.tqg.manifest import TQGCase
    from docmirror.eval.tqg.runner import run_tqg_case

    report = run_tqg_case(
        TQGCase(
            id="unit_geometry",
            track="mirror_geometry",
            pipeline="mirror_geometry_contract",
            oracle={
                "mirror_geometry": {
                    "min_cell_bbox_coverage": 0.9,
                    "require_monotonic_rows": True,
                    "require_monotonic_cols": True,
                    "require_table_bbox_contains_cells": True,
                    "require_row_col_bands": True,
                    "require_logical_source_cell_refs": True,
                }
            },
        )
    )

    assert report.passed, report.failures


def test_core_mirror_geometry_golden_matches_synthetic_contract():
    from docmirror.eval.tqg.manifest import TQGCase
    from docmirror.eval.tqg.runner import run_tqg_case

    golden = json.loads(_CORE_MIRROR_GOLDEN.read_text(encoding="utf-8"))
    report = run_tqg_case(
        TQGCase(
            id=golden["case_id"],
            track="mirror_geometry",
            pipeline="mirror_geometry_contract",
            oracle={
                "mirror_geometry": {
                    "mirror_level": "forensic",
                    "min_physical_tables": 1,
                    "min_cell_bbox_coverage": 0.9,
                    "min_exact_geometry_ratio": 0.8,
                    "max_estimated_geometry_ratio": 0.2,
                    "max_missing_geometry_cells": 0,
                    "require_monotonic_rows": True,
                    "require_monotonic_cols": True,
                    "require_table_bbox_contains_cells": True,
                    "require_row_col_bands": True,
                    "require_logical_source_cell_refs": True,
                    "require_logical_source_refs_resolve": True,
                    "require_physical_cell_source_refs": True,
                    "require_geometry_loss_reason_for_estimated": True,
                    "require_cell_token_ids": True,
                    "require_unique_cell_token_ownership": True,
                    "require_merged_cell_bbox_consistency": True,
                }
            },
        )
    )

    assert report.passed, report.failures
    for check, expected in golden["expected_checks"].items():
        assert report.checks.get(check) is expected
    for metric, expected in golden["expected_metrics"].items():
        assert report.metrics.get(metric) == expected


def test_mirror_geometry_oracle_rejects_missing_cell_bboxes():
    api = {
        "data": {
            "document": {
                "pages": [
                    {
                        "page_number": 1,
                        "tables": [
                            {
                                "table_id": "pt_1_0",
                                "bbox": [0, 0, 100, 40],
                                "rows": [{"cells": [{"text": "1"}]}],
                            }
                        ],
                    }
                ]
            }
        }
    }

    report = run_mirror_geometry_oracle(
        api,
        {"min_cell_bbox_coverage": 0.9, "max_missing_geometry_cells": 0},
        case_id="missing",
    )

    assert not report.passed
    assert any("cell bbox coverage" in failure for failure in report.failures)


def test_mirror_geometry_oracle_rejects_low_exact_geometry_ratio():
    api = {
        "data": {
            "document": {
                "pages": [
                    {
                        "page_number": 1,
                        "tables": [
                            {
                                "table_id": "pt_1_0",
                                "bbox": [0, 0, 20, 10],
                                "rows": [
                                    {
                                        "cells": [
                                            {
                                                "text": "A",
                                                "bbox": [0, 0, 10, 10],
                                                "geometry_status": "estimated",
                                            },
                                            {
                                                "text": "B",
                                                "bbox": [10, 0, 20, 10],
                                                "geometry_status": "estimated",
                                            },
                                        ]
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        }
    }

    report = run_mirror_geometry_oracle(
        api,
        {"min_exact_geometry_ratio": 0.8, "max_estimated_geometry_ratio": 0.2},
        case_id="low_exact",
    )

    assert not report.passed
    assert report.metrics["exact_geometry_ratio"] == 0.0
    assert report.metrics["estimated_geometry_ratio"] == 1.0
    assert any("exact geometry ratio" in failure for failure in report.failures)


def test_mirror_geometry_oracle_rejects_unresolved_logical_source_refs():
    api = {
        "data": {
            "document": {
                "pages": [
                    {
                        "page_number": 1,
                        "tables": [
                            {
                                "table_id": "pt_1_0",
                                "page": 1,
                                "rows": [
                                    {
                                        "source_row_index": 0,
                                        "cells": [
                                            {
                                                "text": "1",
                                                "bbox": [0, 0, 10, 10],
                                                "source_cell_refs": [
                                                    {"page": 1, "table_id": "pt_1_0", "row": 0, "col": 0}
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "logical_tables": [
                    {
                        "rows": [
                            {
                                "source_cell_refs": [
                                    {"page": 1, "table_id": "pt_1_0", "row": 99, "col": 0}
                                ]
                            }
                        ]
                    }
                ],
            }
        }
    }

    report = run_mirror_geometry_oracle(
        api,
        {"require_logical_source_refs_resolve": True},
        case_id="bad_ref",
    )

    assert not report.passed
    assert any("resolve to physical table cells" in failure for failure in report.failures)


def test_mirror_geometry_oracle_rejects_duplicate_cell_token_ownership():
    api = {
        "data": {
            "document": {
                "pages": [
                    {
                        "page_number": 1,
                        "tables": [
                            {
                                "table_id": "pt_1_0",
                                "page": 1,
                                "rows": [
                                    {
                                        "cells": [
                                            {"text": "A", "bbox": [0, 0, 10, 10], "token_ids": ["tok_1"]},
                                            {"text": "B", "bbox": [10, 0, 20, 10], "token_ids": ["tok_1"]},
                                        ]
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        }
    }

    report = run_mirror_geometry_oracle(
        api,
        {"require_unique_cell_token_ownership": True},
        case_id="duplicate_token",
    )

    assert not report.passed
    assert report.metrics["duplicate_cell_token_ownership_count"] == 1
    assert any("belong to one cell" in failure for failure in report.failures)


def test_table_geometry_aggregates_char_refs_and_confidence():
    from docmirror.geometry.table_geometry import build_table_geometry

    geometry = build_table_geometry(
        [["AB"]],
        chars=[
            {"text": "A", "bbox": [0, 0, 10, 10], "token_id": "tok_a", "confidence": 0.8},
            {"text": "B", "bbox": [10, 0, 20, 10], "token_id": "tok_b", "confidence": 0.6},
        ],
        table_bbox=[0, 0, 20, 10],
        page_number=1,
        table_index=0,
        geometry_source="unit_chars",
    )

    attrs = geometry.to_attrs()
    assert attrs["cell_token_ids"][0][0] == ["tok_a", "tok_b"]
    assert attrs["cell_evidence_ids"][0][0] == ["tok_a", "tok_b"]
    assert abs(attrs["cell_confidences"][0][0] - 0.7) < 1e-9


def test_table_geometry_prefers_native_exact_cell_bboxes():
    from docmirror.geometry.table_geometry import build_table_geometry

    geometry = build_table_geometry(
        [["A", "B"]],
        chars=[
            {"text": "A", "bbox": [1, 1, 8, 8], "token_id": "tok_a"},
            {"text": "B", "bbox": [11, 1, 18, 8], "token_id": "tok_b"},
        ],
        table_bbox=[0, 0, 20, 10],
        native_cell_bboxes=[[[0, 0, 10, 10], [10, 0, 20, 10]]],
        page_number=1,
        table_index=0,
        geometry_source="pdfplumber_native",
    )

    attrs = geometry.to_attrs()
    assert attrs["cell_bboxes"][0][0] == [0.0, 0.0, 10.0, 10.0]
    assert attrs["cell_bboxes"][0][1] == [10.0, 0.0, 20.0, 10.0]
    assert attrs["cell_geometry_status"][0] == ["exact", "exact"]
    assert attrs["cell_token_ids"][0] == [["tok_a"], ["tok_b"]]


def test_pdfplumber_native_cell_bboxes_for_table_shape_match():
    from docmirror.geometry.pdfplumber_native import native_cell_bboxes_for_table

    class FakeRow:
        def __init__(self, cells):
            self.cells = cells

    class FakeTable:
        rows = [
            FakeRow([(0, 0, 10, 10), (10, 0, 20, 10)]),
            FakeRow([(0, 10, 10, 20), (10, 10, 20, 20)]),
        ]

    class FakePage:
        def find_tables(self):
            return [FakeTable()]

    bboxes = native_cell_bboxes_for_table(
        FakePage(),
        [["A", "B"], ["1", "2"]],
        table_bbox=[0, 0, 20, 20],
    )

    assert bboxes == [
        [(0.0, 0.0, 10.0, 10.0), (10.0, 0.0, 20.0, 10.0)],
        [(0.0, 10.0, 10.0, 20.0), (10.0, 10.0, 20.0, 20.0)],
    ]
