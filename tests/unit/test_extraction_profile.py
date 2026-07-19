# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ExtractionProfile / EPO components."""

from __future__ import annotations

from pathlib import Path

import pdfplumber
import pytest

from docmirror.layout.profile.registry import get_profile, load_profiles, match_layout_profile
from docmirror.models.entities.extraction_profile import ExtractionProfile, SegmentationMode
from docmirror.tables.best_candidate import ExtractCandidate, pick_best_candidate
from docmirror.tables.cell_normalizer import normalize_cell_text, normalize_table_cells
from docmirror.tables.engine import extract_tables_layered
from docmirror.tables.segmentation import segment_page_for_extraction
from tests.public_fixtures.generate import generate_synthetic_wechat_statement


@pytest.fixture(autouse=True)
def _clear_profile_cache():
    load_profiles.cache_clear()
    yield
    load_profiles.cache_clear()


@pytest.fixture(scope="module")
def public_wechat_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("public-fixtures") / "synthetic_easy_standard.pdf"
    return generate_synthetic_wechat_statement(output)


def test_generic_profile_defaults_preserve_current_behavior():
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


def test_match_bank_reconciliation_scene_to_borderless_profile():
    """bank_reconciliation ledgers must not fall back to generic x_clustering."""
    from docmirror.layout.scene.scene_resolver import scene_to_layout_profile_id

    assert scene_to_layout_profile_id("bank_reconciliation") == "borderless_ledger_bank"

    p = match_layout_profile(
        text_sample="账户明细信息",
        num_pages=11,
        resolved_scene="bank_reconciliation",
        scene_confidence=0.84,
    )
    assert p.profile_id == "borderless_ledger_bank"

    p_hint = match_layout_profile(
        text_sample="",
        num_pages=11,
        scene_hint="bank_reconciliation",
    )
    assert p_hint.profile_id == "borderless_ledger_bank"


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


def test_full_page_segmentation_bbox_covers_page(public_wechat_pdf: Path):
    pdf = public_wechat_pdf
    profile = get_profile("borderless_ledger_wechat")
    with pdfplumber.open(pdf) as doc:
        page = doc.pages[0]
        zones = segment_page_for_extraction(page, 0, profile)
    table_zones = [z for z in zones if z.type == "data_table"]
    assert len(table_zones) == 1
    _x0, y0, x1, y1 = table_zones[0].bbox
    assert y1 >= page.height * 0.95
    assert x1 <= page.width * 0.75


def test_engine_profile_disables_pymupdf_on_wechat_page(public_wechat_pdf: Path):
    pdf = public_wechat_pdf
    profile = get_profile("borderless_ledger_wechat")
    audit: list = []
    with pdfplumber.open(pdf) as doc:
        import fitz

        fitz_doc = fitz.open(pdf)
        page = doc.pages[0]
        fitz_page = fitz_doc[0]
        zones = segment_page_for_extraction(page, 0, profile)
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
    assert len(tables[0]) >= 2
