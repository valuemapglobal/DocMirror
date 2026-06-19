# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.core.ocr.micro_grid.materialize import extract_micro_grid_structures
from docmirror.core.ocr.page_canvas.evidence_bundles import (
    domain_specific_with_page_bundles,
    materialize_micro_grids_from_bundles,
    micro_grid_structures_from_bundles,
    page_evidence_bundle,
)
from tests.unit.test_scanned_micro_grid_repayment import _credit_page4_lines, _credit_page4_tokens


def test_extract_micro_grid_structures_materializes_credit_repayment():
    grids = extract_micro_grid_structures(
        _credit_page4_lines(),
        tokens=_credit_page4_tokens(),
        page=4,
        page_width=834,
        page_height=1207,
    )
    assert len(grids) == 1
    assert grids[0]["grid_id"] == "mg_p4_repayment_0"
    year_cells = [cell for row in grids[0]["cells"] for cell in row if cell.get("role") == "year"]
    assert [cell["text"] for cell in year_cells] == ["2021", "2020"]


def test_materialize_micro_grids_from_bundles_is_idempotent():
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
    first = materialize_micro_grids_from_bundles(ds)
    second = materialize_micro_grids_from_bundles(ds)
    assert len(first) == 1
    assert second == []
    assert micro_grid_structures_from_bundles(ds)[0]["grid_id"] == "mg_p4_repayment_0"
