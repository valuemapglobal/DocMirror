# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Canonical import paths (CPA design 12 ADR-CPA-05)."""

from __future__ import annotations


def test_segment_zones_exports_layout_entrypoints():
    from docmirror.layout.segment.zones import (
        Zone,
        analyze_document_layout,
        segment_page_into_zones,
    )

    assert Zone is not None
    assert callable(analyze_document_layout)
    assert callable(segment_page_into_zones)


def test_segment_exports_layout_helpers():
    from docmirror.layout.segment.graph_router import GraphRouter
    from docmirror.layout.segment.layout_model import LayoutDetector

    assert GraphRouter is not None
    assert LayoutDetector is not None


def test_physical_models_reexport_via_domain_shim():
    from docmirror.models.entities.physical import Block as CanonBlock
    from docmirror.models.entities.physical import PageLayout as CanonPage
    from docmirror.models.entities.domain import Block, PageLayout

    assert Block is CanonBlock
    assert PageLayout is CanonPage


def test_ocr_uop_subpackages_reexport_pipeline_symbols():
    from docmirror.ocr.postprocess.generic import postprocess_ocr_text
    from docmirror.ocr.preprocess import preprocess_image_for_ocr
    from docmirror.ocr.recognize import get_ocr_engine
    from docmirror.ocr.reconstruct import reconstruct_table_grid_2d

    assert callable(preprocess_image_for_ocr)
    assert callable(get_ocr_engine)
    assert callable(reconstruct_table_grid_2d)
    assert callable(postprocess_ocr_text)
