# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.models.mirror.page_evidence_bundles import (
    domain_specific_with_page_bundles,
    micro_grid_structures_from_bundles,
    page_evidence_bundle,
)
from docmirror.plugins.credit_report.micro_grid_materialize import (
    augment_credit_repayment_evidence_bundles,
    materialize_credit_repayment_micro_grids,
    materialize_credit_repayment_micro_grids_from_bundles,
)
from docmirror.plugins.credit_report.repayment_grid import records_from_micro_grid_dict
from tests.unit.test_scanned_micro_grid_repayment import _credit_page4_lines, _credit_page4_tokens


def test_materialize_credit_repayment_micro_grids_materializes_credit_repayment():
    grids = materialize_credit_repayment_micro_grids(
        lines=_credit_page4_lines(),
        tokens=_credit_page4_tokens(),
        page=4,
        page_width=834,
        page_height=1207,
    )
    assert len(grids) == 1
    assert grids[0]["grid_id"] == "mg_p4_repayment_0"
    year_cells = [cell for row in grids[0]["cells"] for cell in row if cell.get("role") == "year"]
    assert [cell["text"] for cell in year_cells] == ["2021", "2020"]


def test_materialize_credit_repayment_micro_grids_from_bundles_is_idempotent():
    ds = domain_specific_with_page_bundles(
        page_evidence_bundle(
            4,
            page_width=834,
            page_height=1207,
            micro_grid_evidence={
                "page": 4,
                "page_width": 834,
                "page_height": 1207,
                "lines": _credit_page4_lines(),
                "tokens": [token.to_dict() for token in _credit_page4_tokens()],
            },
        ),
    )
    first = materialize_credit_repayment_micro_grids_from_bundles(ds)
    second = materialize_credit_repayment_micro_grids_from_bundles(ds)
    assert len(first) == 1
    assert second == []
    assert micro_grid_structures_from_bundles(ds)[0]["grid_id"] == "mg_p4_repayment_0"


def test_multiple_date_range_anchors_materialize_without_dropping_unresolved_grid() -> None:
    lines = [
        {"text": "2024年01月-2024年02月的还款记录", "bbox": [100, 100, 300, 115]},
        {"text": "1 2 3 4 5 6 7 8 9 10 11 12", "bbox": [50, 118, 500, 132]},
        {"text": "N N", "bbox": [50, 135, 120, 148]},
        {"text": "2024 0 0", "bbox": [20, 150, 120, 164]},
        {"text": "2025年07月-2025年09月的还款记录", "bbox": [100, 300, 300, 315]},
    ]

    grids = materialize_credit_repayment_micro_grids(lines=lines, page=5, page_width=600, page_height=800)

    assert [grid["grid_id"] for grid in grids] == ["mg_p5_repayment_0", "mg_p5_repayment_1"]
    assert len(records_from_micro_grid_dict(grids[0])) == 2
    unresolved = records_from_micro_grid_dict(grids[1])
    assert len(unresolved) == 3
    assert {record["status"] for record in unresolved} == {"unknown"}


def test_cross_page_leading_rows_are_appended_only_to_micro_grid_evidence() -> None:
    first_lines = [{"text": "2022年11月-2023年02月的还款记录", "bbox": [100, 700, 300, 715]}]
    second_lines = [
        {"text": "N N", "bbox": [200, 20, 260, 32]},
        {"text": "2023 0 0", "bbox": [20, 35, 260, 48]},
        {"text": "账户2(授信协议标识:X)", "bbox": [20, 80, 300, 95]},
    ]
    ds = {
        "_page_evidence_bundles": [
            {
                "page": 4,
                "page_height": 800,
                "micro_grid_evidence": {"page": 4, "page_height": 800, "lines": first_lines},
            },
            {"page": 5, "micro_grid_evidence": {"page": 5, "lines": second_lines}},
        ]
    }

    augment_credit_repayment_evidence_bundles(ds)

    evidence = ds["_page_evidence_bundles"][0]["micro_grid_evidence"]
    assert len(evidence["lines"]) == 3
    assert evidence["lines"][-1]["source_logical_page"] == 5
    assert evidence["lines"][-1]["bbox"][1] == 835
