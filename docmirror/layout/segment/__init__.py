# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Segment package — layout analysis and semantic zone partitioning."""

from __future__ import annotations

__all__ = [
    "Zone",
    "GraphRouter",
    "LayoutDetector",
    "analyze_document_layout",
    "analyze_document_layout_parallel",
    "analyze_page_layout",
    "segment_page_into_zones",
]

_LAZY_EXPORTS = {
    "Zone": ("docmirror.layout.segment.zones", "Zone"),
    "analyze_document_layout": ("docmirror.layout.segment.zones", "analyze_document_layout"),
    "analyze_document_layout_parallel": ("docmirror.layout.segment.zones", "analyze_document_layout_parallel"),
    "analyze_page_layout": ("docmirror.layout.segment.zones", "analyze_page_layout"),
    "segment_page_into_zones": ("docmirror.layout.segment.zones", "segment_page_into_zones"),
    "GraphRouter": ("docmirror.layout.segment.graph_router", "GraphRouter"),
    "LayoutDetector": ("docmirror.layout.segment.layout_model", "LayoutDetector"),
}


def __getattr__(name: str):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    from importlib import import_module

    value = getattr(import_module(module_name), attr)
    globals()[name] = value
    return value
