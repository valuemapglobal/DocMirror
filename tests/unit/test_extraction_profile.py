# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ExtractionProfile / EPO components."""

from __future__ import annotations

import pdfplumber
import pytest

from docmirror.core.layout.profile_registry import get_profile, load_profiles, match_layout_profile
from docmirror.core.table.extraction.best_candidate import ExtractCandidate, pick_best_candidate
from docmirror.core.table.extraction.cell_normalizer import normalize_cell_text, normalize_table_cells
from docmirror.core.table.extraction.engine import extract_tables_layered
from docmirror.core.table.extraction.segmentation import segment_page_for_extraction
from docmirror.models.entities.extraction_profile import ExtractionProfile, SegmentationMode


@pytest.fixture(autouse=True)
def _clear_profile_cache():
    load_profiles.cache_clear()
    yield
    load_profiles.cache_clear()


def test_generic_profile_defaults_preserve_legacy():
    p = get_profile("generic")
    assert p.segmentation_mode == SegmentationMode.ZONE
    assert p.enable_best_candidate_selection is False
    assert p.min_confidence_to_accept == 0.0
    assert p.normalize_intracellular_newlines is False


def test_wechat_profile_epo_fields():
    p = get_profile("borderless_ledger_wechat")
    assert p.is_full_page_table()
    assert p.enable_best_candidate_selection is True
    assert p.enable_grid_template is True
    assert "pymupdf_native" in p.table_disabled_layers()
    assert p.normalize_intracellular_newlines is True
    assert len(p.expected_header_columns) == 8


def test_match_wechat_by_text():
    p = match_layout_profile(
        text_sample="微信支付交易明细证明 财付通",
        num_pages=219,
    )
    assert p.profile_id == "borderless_ledger_wechat"


def test_cell_normalizer_strips_id_newlines():
    p = get_profile("borderless_ledger_wechat")
    raw = "4200001\n234567890"
    out = normalize_cell_text(raw, profile=p)
    assert "\n" not in out
    assert " " not in out


def test_bcs_picks_pdfplumber_over_inflated_char_layer():
    p = get_profile("borderless_ledger_wechat")
    low = ExtractCandidate(
        tables=[[["h"] * 8] + [["a"] * 8] * 20],
        layer="pymupdf_native",
        confidence=0.53,
    )
    high = ExtractCandidate(
        tables=[[["h"] * 8] + [["a"] * 8] * 22],
        layer="pdfplumber_default",
        confidence=0.91,
    )
    inflated = ExtractCandidate(
        tables=[[["h"] * 8] + [["a"] * 8] * 30],
        layer="word_anchors",
        confidence=0.49,
    )
    pick = pick_best_candidate([low, inflated, high], p, oracle_rows=22)
    assert pick is not None
    assert pick.candidate.layer == "pdfplumber_default"


def test_full_page_segmentation_bbox_covers_page():
    pdf = "tests/fixtures/wechat_payment/DemoUser+微信流水.pdf"
    profile = get_profile("borderless_ledger_wechat")
    with pdfplumber.open(pdf) as doc:
        page = doc.pages[1]
        zones = segment_page_for_extraction(page, 1, profile)
    table_zones = [z for z in zones if z.type == "data_table"]
    assert len(table_zones) == 1
    _x0, y0, x1, y1 = table_zones[0].bbox
    assert y1 >= page.height * 0.95
    assert x1 <= page.width * 0.75


def test_engine_profile_disables_pymupdf_on_wechat_page():
    pdf = "tests/fixtures/wechat_payment/DemoUser+微信流水.pdf"
    profile = get_profile("borderless_ledger_wechat")
    audit: list = []
    with pdfplumber.open(pdf) as doc:
        import fitz

        fitz_doc = fitz.open(pdf)
        page = doc.pages[2]
        fitz_page = fitz_doc[2]
        zones = segment_page_for_extraction(page, 2, profile)
        bbox = next(z.bbox for z in zones if z.type == "data_table")
        tables, layer, conf = extract_tables_layered(
            page,
            table_zone_bbox=bbox,
            fitz_page=fitz_page,
            extraction_profile=profile,
            extraction_audit=audit,
        )
        fitz_doc.close()
    assert layer != "pymupdf_native"
    assert len(tables[0]) >= 20
