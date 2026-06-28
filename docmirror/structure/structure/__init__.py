# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Document Flow Graph (DFG) detection engine — universal geometry-based structure recovery.

This package implements the detection/computation layer for document-level structure.
It reads Mirror facts (pages, blocks, bboxes) and produces DFG v2 output consumed by
``docmirror.models.mirror.document_structure.build_document_structure()``.

Modules:
    column_detector: XY-Cut recursive projection column detection
    reading_order: Column-major intra-page sort + inter-page continuity
    section_tree: Multi-language header detection + indent clustering
    cross_page: Adjacent page boundary block overlap + text continuity
    dfg_engine: Orchestrator that builds the full DocumentFlowGraph
"""

from __future__ import annotations

from docmirror.structure.structure.column_detector import (
    ColumnAssignment,
    ColumnLayout,
    detect_columns,
    detect_columns_from_pages,
)
from docmirror.structure.structure.cross_page import (
    BridgeList,
    CrossPageBridge,
    detect_cross_page_bridges,
)
from docmirror.structure.structure.dfg_engine import (
    DFGEngine,
    build_dfg,
)
from docmirror.structure.structure.reading_order import (
    OrderedBlock,
    OrderedPage,
    ReadingFlow,
    compute_reading_order,
)
from docmirror.structure.structure.section_tree import (
    SectionNode,
    SectionTree,
    build_section_tree,
    detect_headings,
)

__all__ = [
    "ColumnAssignment",
    "ColumnLayout",
    "detect_columns",
    "detect_columns_from_pages",
    "CrossPageBridge",
    "BridgeList",
    "detect_cross_page_bridges",
    "DFGEngine",
    "build_dfg",
    "OrderedBlock",
    "OrderedPage",
    "ReadingFlow",
    "compute_reading_order",
    "SectionNode",
    "SectionTree",
    "build_section_tree",
    "detect_headings",
]
