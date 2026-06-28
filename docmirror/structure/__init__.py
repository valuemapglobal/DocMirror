# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""UDTR core building blocks."""

from docmirror.structure.evidence_plane import (
    DocumentSource,
    EvidencePage,
    EvidencePlane,
    EvidencePlaneBuilder,
)
from docmirror.structure.page_topology import (
    DocumentTopology,
    PageTopology,
    PageTopologyBuilder,
    TopologyRegion,
)
from docmirror.structure.reconstructors import (
    KeyValueGroupRegionReconstructor,
    ReconstructionContext,
    RegionReconstructor,
    RegionReconstructorRegistry,
    ResidualRegionReconstructor,
    TableLikeRegionReconstructor,
    TextRegionReconstructor,
    TocRegionReconstructor,
    VisualRegionReconstructor,
)

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
