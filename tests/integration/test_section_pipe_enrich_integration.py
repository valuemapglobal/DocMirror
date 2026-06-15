# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration: section-led PDF with embedded pipe ledger enrich (Phase 3)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.tier_regression]

from docmirror.core.extraction.strategies.section_driven import SectionDrivenStrategy
from tests.unit.test_section_driven_pipe_enrich import _FakePreAnalysis

CREDIT = Path("tests/fixtures/synthetic/credit_report_section_smoke.pdf")
BOC = Path("tests/fixtures/bank_statement/中国银行-南京创沃电气设备有限公司_1.pdf")


def _merge_credit_and_pipe_page(out_path: Path) -> None:
    import fitz

    credit = fitz.open(str(CREDIT))
    boc = fitz.open(str(BOC))
    credit.insert_pdf(boc, from_page=0, to_page=0)
    credit.save(str(out_path))
    credit.close()
    boc.close()


def test_section_pipe_enrich_on_merged_fixture_pdf(tmp_path):
    if not CREDIT.is_file() or not BOC.is_file():
        pytest.skip("missing credit_report or BOC fixture")

    pdf_path = tmp_path / "credit_plus_pipe_page.pdf"
    _merge_credit_and_pipe_page(pdf_path)

    import fitz

    fitz_doc = fitz.open(str(pdf_path))
    try:
        pre = _FakePreAnalysis(
            structure_spe={
                "primary": "section_led",
                "competitors": {"H_section": 0.72, "H_pipe_grid": 0.1},
                "table_extraction": "skipped",
                "table_extraction_skipped_reason": "route_section_dominant",
                "sso_version": "1.0",
            }
        )
        pages, full_text, layer, _conf, perf, _ = SectionDrivenStrategy().extract(fitz_doc, pre)
    finally:
        fitz_doc.close()

    assert layer == "section_driven"
    assert perf.get("pipe_table_enrich") is True
    table_count = sum(1 for p in pages for b in p.blocks if b.block_type == "table")
    assert table_count >= 1
    assert "序号" in full_text or "记账日" in full_text
