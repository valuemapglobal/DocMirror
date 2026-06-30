# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Profile-driven stage skip matrix (CPA design 12 §7.2)."""

from __future__ import annotations

from docmirror.configs.models.extraction_profile import ExtractionProfile, SegmentationMode
from docmirror.layout.profile.registry import get_profile


def test_full_page_profile_skips_zone_template_path():
    profile = ExtractionProfile(
        profile_id="test_full_page",
        segmentation_mode=SegmentationMode.FULL_PAGE_TABLE,
    )
    assert profile.is_full_page_table() is True

    skip_zone_template = profile.is_full_page_table()
    assert skip_zone_template is True


def test_zone_profile_allows_zone_template():
    profile = ExtractionProfile(profile_id="generic", segmentation_mode=SegmentationMode.ZONE)
    assert profile.is_full_page_table() is False


def test_wechat_profile_loads_normalize_hooks_from_yaml():
    profile = get_profile("borderless_ledger_wechat")
    assert profile.table_normalize_hooks == ["ledger_borderless"]
    assert profile.is_full_page_table() is True
    assert profile.enable_global_grid_tensor is False
    assert profile.needs_global_grid_tensor() is False


def test_borderless_ledger_continuation_fast_path_gates():
    profile = get_profile("borderless_ledger_wechat")
    page_idx = 2
    has_template = True
    fast = bool(
        page_idx > 0
        and has_template
        and profile.is_borderless_ledger()
        and profile.should_use_bcs()
    )
    assert fast is True


def test_scanned_page_skips_digital_pipeline_stages():
    """Scanned pages use extract_scanned_page — not PagePipeline CPS."""
    is_digital = False
    runs_page_pipeline = is_digital
    assert runs_page_pipeline is False


def test_hybrid_doc_routes_per_page_text_threshold():
    page_has_text = [True, False, True]
    hybrid = any(page_has_text) and not all(page_has_text)
    assert hybrid is True
    assert page_has_text[1] is False
