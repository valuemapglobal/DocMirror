# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from pathlib import Path

import pytest

from docmirror.plugins.credit_report.repayment_grid import extract_credit_repayment_records
from tests._scanned_ocr_helpers import ocr_page_as_pdf_points


_FIXTURE = Path("tests/fixtures/synthetic/credit_report_section_smoke.pdf")


pytestmark = [
    pytest.mark.slow,
    pytest.mark.track_scanned_micro_grid,
]


@pytest.mark.skipif(
    os.environ.get("DOCMIRROR_RUN_REAL_OCR") != "1",
    reason="set DOCMIRROR_RUN_REAL_OCR=1 to run real scanned PDF OCR gate",
)
@pytest.mark.skipif(not _FIXTURE.exists(), reason="credit report fixture is not available")
def test_real_credit_report_page4_scanned_micro_grid_gate():
    fitz = pytest.importorskip("fitz")

    with fitz.open(_FIXTURE) as doc:
        page_index = 3
        page = doc[page_index]
        ocr, lines, tokens = ocr_page_as_pdf_points(page, page_index)
        assert ocr and ocr.get("content_type") == "general"

        out = extract_credit_repayment_records(
            lines,
            page=4,
            tokens=tokens,
            page_width=page.rect.width,
            page_height=page.rect.height,
            page_image=ocr.get("_page_image"),
            enable_cell_ocr=True,
        )

    assert [
        (r["year"], r["month"], r["status"], r["overdue_amount"])
        for r in out["repayment_records"]
    ] == [
        (2021, 1, "N", "0"),
        (2021, 2, "C", "0"),
        (2020, 9, "N", "0"),
        (2020, 10, "N", "0"),
        (2020, 11, "N", "0"),
        (2020, 12, "N", "0"),
    ]
    assert out["micro_grid"]["audit"]["cell_crop_ocr"]["enabled"] is True
