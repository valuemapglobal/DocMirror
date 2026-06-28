# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Document Flow Graph (DFG) orchestrator.

Orchestrates all four DFG phases and produces a DocumentFlowGraph consumable by
``docmirror.models.mirror.document_structure.build_document_structure()``.

Pipeline:
    1. Column Detector — XY-Cut recursive projection
    2. Reading Order — Column-major intra-page sort
    3. Section Tree — Multi-language heading detection + clustering
    4. Cross-page Continuity — Bridge detection

The engine reads Mirror facts (pages, blocks) and produces DFG v2 output.
It never modifies Mirror data.
"""

from __future__ import annotations

import logging
from typing import Any

from docmirror.structure.structure.column_detector import (
    ColumnLayout,
    detect_columns_from_pages,
)
from docmirror.structure.structure.cross_page import (
    BridgeList,
    CrossPageBridge,
    detect_cross_page_bridges,
)
from docmirror.structure.structure.reading_order import (
    ReadingFlow,
    compute_reading_order,
)
from docmirror.structure.structure.section_tree import (
    SectionNode,
    SectionTree,
    build_section_tree,
    detect_headings,
)

logger = logging.getLogger(__name__)

# ── DFG profile configuration ──────────────────────────────────────────────────
DFG_PROFILES: dict[str, dict[str, Any]] = {
    "quickstart": {
        "column_detection": True,
        "section_tree": False,
        "cross_page": False,
        "min_blocks_for_columns": 6,
        "description": "Fastest — reading order only, no section tree",
    },
    "compact": {
        "column_detection": True,
        "section_tree": True,
        "cross_page": False,
        "min_blocks_for_columns": 4,
        "description": "Reading order + section tree, no cross-page merging",
    },
    "full": {
        "column_detection": True,
        "section_tree": True,
        "cross_page": True,
        "min_blocks_for_columns": 4,
        "description": "Full DFG: columns, section tree, cross-page bridges",
    },
    "ga_full": {
        "column_detection": True,
        "section_tree": True,
        "cross_page": True,
        "min_blocks_for_columns": 3,
        "description": "GA complete — maximum structure recovery",
    },
    "forensic": {
        "column_detection": True,
        "section_tree": True,
        "cross_page": True,
        "min_blocks_for_columns": 2,
        "description": "Forensic — everything, including low-quality signals",
    },
}


class DFGEngine:
    """Orchestrator for Document Flow Graph construction.

    Usage::

        engine = DFGEngine(profile="ga_full")
        dfg = engine.build(mirror_pages)
        # dfg is a dict consumable by build_document_structure()
    """

    def __init__(self, *, profile: str = "ga_full", config: dict[str, Any] | None = None):
        self._profile = profile
        self._config = config or DFG_PROFILES.get(profile, DFG_PROFILES["full"])

    @property
    def profile(self) -> str:
        return self._profile

    def build(self, pages: list[dict[str, Any]]) -> dict[str, Any]:
        """Execute all DFG phases and return a complete DFG dict.

        Args:
            pages: List of page dicts with page_number, blocks/texts, width, height.

        Returns:
            Dict with keys: column_layout, reading_flow, section_tree, cross_page_bridges,
            quality, profile.
        """
        result: dict[str, Any] = {
            "profile": self._profile,
            "column_layout": None,
            "reading_flow": None,
            "section_tree": None,
            "cross_page_bridges": None,
            "quality": {
                "column_detection_ran": False,
                "column_detection_degraded": False,
                "reading_order_degraded": False,
                "section_tree_built": False,
                "cross_page_detected": False,
            },
        }

        if not pages:
            result["quality"]["reading_order_degraded"] = True
            return result

        # ── Phase 1: Column Detection ──
        column_layout: ColumnLayout | None = None

        if self._config.get("column_detection", True):
            try:
                min_blocks = self._config.get("min_blocks_for_columns", 4)
                column_layout = detect_columns_from_pages(
                    pages,
                    min_block_count=min_blocks,
                )
                result["column_layout"] = _column_layout_to_dict(column_layout)
                result["quality"]["column_detection_ran"] = True
                result["quality"]["column_detection_degraded"] = any(
                    a.degraded for a in column_layout.pages.values()
                )
            except Exception as exc:
                logger.warning("DFG column detection failed: %s", exc, exc_info=True)
                result["quality"]["column_detection_degraded"] = True

        # ── Phase 2: Reading Order ──
        try:
            reading_flow = compute_reading_order(pages, column_layout=column_layout)
            result["reading_flow"] = _reading_flow_to_dict(reading_flow)
            if reading_flow.degraded_pages:
                result["quality"]["reading_order_degraded"] = True
        except Exception as exc:
            logger.warning("DFG reading order failed: %s", exc, exc_info=True)
            result["quality"]["reading_order_degraded"] = True

        # ── Phase 3: Section Tree ──
        if self._config.get("section_tree", False):
            try:
                all_headings: list[SectionNode] = []
                for page in pages:
                    blocks = page.get("blocks") or page.get("texts") or []
                    if blocks:
                        page_num = int(page.get("page_number") or 0)
                        headings = detect_headings(blocks, page_number=page_num)
                        all_headings.extend(headings)

                section_tree = build_section_tree(all_headings)
                result["section_tree"] = _section_tree_to_dict(section_tree)
                result["quality"]["section_tree_built"] = True
            except Exception as exc:
                logger.warning("DFG section tree failed: %s", exc, exc_info=True)

        # ── Phase 4: Cross-page Continuity ──
        if self._config.get("cross_page", False):
            try:
                bridges = detect_cross_page_bridges(pages)
                result["cross_page_bridges"] = _bridge_list_to_dict(bridges)
                if bridges.confirmed_count > 0:
                    result["quality"]["cross_page_detected"] = True
            except Exception as exc:
                logger.warning("DFG cross-page detection failed: %s", exc, exc_info=True)

        return result


def build_dfg(pages: list[dict[str, Any]], *, profile: str = "ga_full") -> dict[str, Any]:
    """Convenience function: build DFG from pages in one call.

    Equivalent to ``DFGEngine(profile=profile).build(pages)``.

    Args:
        pages: List of page dicts.
        profile: DFG profile name.

    Returns:
        DFG dict consumable by build_document_structure().
    """
    engine = DFGEngine(profile=profile)
    return engine.build(pages)


# ── Serialization helpers ──────────────────────────────────────────────────────


def _column_layout_to_dict(layout: ColumnLayout) -> dict[str, Any]:
    """Serialize ColumnLayout to dict."""
    pages_dict: dict[str, Any] = {}
    for page_num, assignment in layout.pages.items():
        pages_dict[str(page_num)] = {
            "page_number": assignment.page_number,
            "columns": assignment.columns,
            "gap_positions": assignment.gap_positions,
            "confidence": assignment.confidence,
            "degraded": assignment.degraded,
        }
    return {"pages": pages_dict, "total_pages_with_columns": len(layout.pages)}


def _reading_flow_to_dict(flow: ReadingFlow) -> dict[str, Any]:
    """Serialize ReadingFlow to dict."""
    global_order = [
        {
            "block_index": ob.block_index,
            "page_number": ob.page_number,
            "reading_order": ob.reading_order,
            "column_id": ob.column_id,
            "bbox": ob.bbox,
            "node_id": ob.node_id,
        }
        for ob in flow.global_order
    ]
    degraded = flow.degraded_pages
    return {
        "global_order": global_order,
        "total_blocks": flow.total_blocks,
        "degraded_pages": degraded,
        "degraded": len(degraded) > 0,
    }


def _section_tree_to_dict(tree: SectionTree) -> dict[str, Any]:
    """Serialize SectionTree to dict."""
    headings = [
        {
            "node_id": h.node_id,
            "title": h.title,
            "level": h.level,
            "page_number": h.page_number,
            "confidence": h.confidence,
        }
        for h in tree.flat_headings
    ]

    def _serialize_node(node: SectionNode) -> dict[str, Any]:
        return {
            "node_id": node.node_id,
            "title": node.title,
            "level": node.level,
            "page_number": node.page_number,
            "confidence": node.confidence,
            "children": [_serialize_node(c) for c in node.children],
        }

    return {
        "root": _serialize_node(tree.root) if tree.root else None,
        "flat_headings": headings,
        "max_depth": tree.max_depth,
        "total_headings": tree.total_headings,
        "confidence": tree.confidence,
    }


def _bridge_list_to_dict(bridge_list: BridgeList) -> dict[str, Any]:
    """Serialize BridgeList to dict."""
    bridges = [
        {
            "bridge_id": b.bridge_id,
            "page_a": b.page_a,
            "block_a_index": b.block_a_index,
            "page_b": b.page_b,
            "block_b_index": b.block_b_index,
            "confidence": b.confidence,
            "evidence": b.evidence,
            "is_candidate": b.is_candidate,
        }
        for b in bridge_list.bridges
    ]
    return {
        "bridges": bridges,
        "confirmed_count": bridge_list.confirmed_count,
        "candidate_count": bridge_list.candidate_count,
    }


__all__ = [
    "DFGEngine",
    "DFG_PROFILES",
    "build_dfg",
]
