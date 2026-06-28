# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""UDTR core building blocks.

Exports are resolved lazily so importing a structure submodule does not
initialize OCR, table, or topology internals.
"""

from __future__ import annotations

__all__ = [
    "DocumentSource",
    "DocumentTopology",
    "EvidencePage",
    "EvidencePlane",
    "EvidencePlaneBuilder",
    "KeyValueGroupRegionReconstructor",
    "PageTopology",
    "PageTopologyBuilder",
    "ReconstructionContext",
    "RegionReconstructor",
    "RegionReconstructorRegistry",
    "ResidualRegionReconstructor",
    "TableLikeRegionReconstructor",
    "TextRegionReconstructor",
    "TopologyRegion",
    "TocRegionReconstructor",
    "VisualRegionReconstructor",
]

_LAZY_EXPORTS = {
    "DocumentSource": ("docmirror.structure.evidence_plane", "DocumentSource"),
    "EvidencePage": ("docmirror.structure.evidence_plane", "EvidencePage"),
    "EvidencePlane": ("docmirror.structure.evidence_plane", "EvidencePlane"),
    "EvidencePlaneBuilder": ("docmirror.structure.evidence_plane", "EvidencePlaneBuilder"),
    "DocumentTopology": ("docmirror.structure.page_topology", "DocumentTopology"),
    "PageTopology": ("docmirror.structure.page_topology", "PageTopology"),
    "PageTopologyBuilder": ("docmirror.structure.page_topology", "PageTopologyBuilder"),
    "TopologyRegion": ("docmirror.structure.page_topology", "TopologyRegion"),
    "KeyValueGroupRegionReconstructor": (
        "docmirror.structure.reconstructors",
        "KeyValueGroupRegionReconstructor",
    ),
    "ReconstructionContext": ("docmirror.structure.reconstructors", "ReconstructionContext"),
    "RegionReconstructor": ("docmirror.structure.reconstructors", "RegionReconstructor"),
    "RegionReconstructorRegistry": ("docmirror.structure.reconstructors", "RegionReconstructorRegistry"),
    "ResidualRegionReconstructor": ("docmirror.structure.reconstructors", "ResidualRegionReconstructor"),
    "TableLikeRegionReconstructor": ("docmirror.structure.reconstructors", "TableLikeRegionReconstructor"),
    "TextRegionReconstructor": ("docmirror.structure.reconstructors", "TextRegionReconstructor"),
    "TocRegionReconstructor": ("docmirror.structure.reconstructors", "TocRegionReconstructor"),
    "VisualRegionReconstructor": ("docmirror.structure.reconstructors", "VisualRegionReconstructor"),
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
