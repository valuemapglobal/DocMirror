# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.configs.models.extraction_profile import ExtractionProfile
from docmirror.core.pipeline import DocumentPipeline, PagePipeline
from docmirror.core.profile.registry import should_skip_cross_page_merge


def test_pipeline_types_importable():
    assert DocumentPipeline is not None
    assert PagePipeline is not None


def test_page_pipeline_declares_cps_stages():
    assert PagePipeline.STAGES == ("prepare", "segment", "assemble", "finalize")


def test_document_pipeline_exposes_profile_and_compose():
    assert callable(DocumentPipeline.bind_profile)
    assert callable(DocumentPipeline.compose_logical_tables)


def test_ledger_continuation_profile_gates_fast_path():
    """Page 2+ ledger continuation requires borderless profile + BCS."""
    profile = ExtractionProfile(profile_id="borderless_ledger_wechat", enable_best_candidate_selection=True)
    assert profile.is_borderless_ledger()
    assert profile.should_use_bcs()

    generic = ExtractionProfile(profile_id="generic_table")
    assert not generic.is_borderless_ledger()

    page_idx = 1
    has_template = True
    fast_continuation = bool(
        page_idx > 0 and has_template and profile.is_borderless_ledger() and profile.should_use_bcs()
    )
    assert fast_continuation is True

    fast_generic = bool(
        page_idx > 0 and has_template and generic.is_borderless_ledger() and generic.should_use_bcs()
    )
    assert fast_generic is False


def test_skip_pid_resample_profile_flag():
    profile = ExtractionProfile(profile_id="borderless_ledger_wechat", skip_pid_resample=True)
    assert profile.skip_pid_resample is True


def test_mirror_skip_cross_page_merge_from_layout_profile():
    profile = ExtractionProfile(profile_id="borderless_ledger_wechat", mirror_skip_cross_page_merge=True)
    assert should_skip_cross_page_merge(profile) is True

    profile_off = ExtractionProfile(profile_id="generic_table", mirror_skip_cross_page_merge=False)
    assert should_skip_cross_page_merge(profile_off) is False
