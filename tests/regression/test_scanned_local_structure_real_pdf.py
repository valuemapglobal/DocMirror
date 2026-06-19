# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from pathlib import Path

import pytest

from docmirror.core.ocr.local_structure import extract_local_structure_evidence
from docmirror.plugins.credit_report.account_structure import extract_credit_accounts_from_local_structure_evidence
from tests._scanned_ocr_helpers import ocr_page_as_pdf_points


_FIXTURE = Path("tests/fixtures/credit_report/兰瑞存_征信详版_拆分.pdf")


pytestmark = [
    pytest.mark.slow,
    pytest.mark.track_scanned_local_structure,
]


@pytest.mark.skipif(
    os.environ.get("DOCMIRROR_RUN_REAL_OCR") != "1",
    reason="set DOCMIRROR_RUN_REAL_OCR=1 to run real scanned PDF OCR gate",
)
@pytest.mark.skipif(not _FIXTURE.exists(), reason="credit report fixture is not available")
def test_real_credit_report_page4_scanned_local_structure_gate():
    fitz = pytest.importorskip("fitz")

    with fitz.open(_FIXTURE) as doc:
        page_index = 3
        page = doc[page_index]
        ocr, lines, tokens = ocr_page_as_pdf_points(page, page_index)
        assert ocr and ocr.get("content_type") == "general"

        evidence = extract_local_structure_evidence(
            lines,
            tokens=tokens,
            page=4,
            page_width=page.rect.width,
            page_height=page.rect.height,
            page_image=ocr.get("_page_image"),
            enable_region_ocr=True,
        )
        out = extract_credit_accounts_from_local_structure_evidence(
            [{"page": 4, "structures": evidence.get("structures") or []}]
        )

    assert len(evidence["structures"]) >= 3
    assert len(out["credit_accounts"]) >= 3
    first = out["credit_accounts"][0]
    assert first["management_institution"]["bbox"]
    assert first["account_identifier"]["source_refs"].get("token_ids") or first["account_identifier"]["source_refs"].get("line_ids")
    assert first["open_date"]["value"] == "2018.08.31"
    assert first["due_date"]["value"] == "2019.06.21"
    assert first["loan_amount"]["value"] == "72000"
    structure_kinds = {s.get("structure_kind") for s in evidence.get("structures") or []}
    assert "field_grid" in structure_kinds
    for account in out["credit_accounts"][:3]:
        assert account["audit"].get("field_source") == "local_structure_field_grid"
        assert account["audit"]["field_count"] >= 6
        assert "1000648287831" in account["account_identifier"]["value"] or "蚂蚁借呗" in account["account_identifier"]["value"] or account["account_identifier"]["value"]
