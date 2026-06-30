# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0


def test_segment_graph_router_importable():
    from docmirror.layout.segment.graph_router import GraphRouter

    router = GraphRouter(page_width=595, page_height=842)
    assert router is not None


def test_segment_layout_detector_importable():
    from docmirror.layout.segment.layout_model import LayoutDetector

    assert LayoutDetector is not None


def test_framework_security_forgery():
    from docmirror.framework.security.forgery_detector import detect_pdf_forgery

    assert callable(detect_pdf_forgery)
