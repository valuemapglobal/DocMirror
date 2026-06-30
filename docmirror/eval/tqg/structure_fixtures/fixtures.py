# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Structure fixture definitions for GA 1.0 release gates (STR-6-1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FixtureSpec:
    """A structure fixture test specification.

    Each fixture defines input page data and expected DFG v2 structure checks
    for the TQG document_structure oracle.
    """

    case_id: str
    description: str
    tier: str = "ga_full"  # raw, structure_v2, ga_full, forensic
    # Input: simulated page data with texts, images, formulas, tables
    pages: list[dict[str, Any]] = field(default_factory=list)
    # Expected DFG v2 checks
    spec: dict[str, Any] = field(default_factory=dict)


# ── Fixture definitions ──────────────────────────────────────────────────────

STRUCTURE_FIXTURES: list[FixtureSpec] = [
    # ── Multi-column reading order ─────────────────────────────────────────
    FixtureSpec(
        case_id="multi_column_reading_order",
        description="Two-column layout: column A (left) read top-to-bottom, then column B (right)",
        tier="ga_full",
        pages=[
            {
                "page_number": 1,
                "texts": [
                    {
                        "content": "Column A paragraph 1.",
                        "level": "body",
                        "reading_order": 1,
                        "bbox": [50, 100, 250, 130],
                        "mirror_role": "body",
                    },
                    {
                        "content": "Column B paragraph 1.",
                        "level": "body",
                        "reading_order": 2,
                        "bbox": [300, 100, 500, 130],
                        "mirror_role": "body",
                    },
                    {
                        "content": "Column A paragraph 2.",
                        "level": "body",
                        "reading_order": 3,
                        "bbox": [50, 150, 250, 180],
                        "mirror_role": "body",
                    },
                    {
                        "content": "Column B paragraph 2.",
                        "level": "body",
                        "reading_order": 4,
                        "bbox": [300, 150, 500, 180],
                        "mirror_role": "body",
                    },
                ],
            }
        ],
        spec={
            "min_dfg_nodes": 4,
            "require_reading_flow": True,
            "require_dfg_node_types": {"paragraph"},
        },
    ),
    # ── Header / Footer detection ──────────────────────────────────────────
    FixtureSpec(
        case_id="repeated_header_footer",
        description="Multi-page document with repeated header and footer on each page",
        tier="ga_full",
        pages=[
            {
                "page_number": 1,
                "texts": [
                    {
                        "content": "Company Report 2026",
                        "level": "body",
                        "reading_order": 1,
                        "bbox": [200, 20, 400, 40],
                        "mirror_role": "header",
                    },
                    {
                        "content": "Section 1: Introduction",
                        "level": "h1",
                        "reading_order": 2,
                        "bbox": [50, 80, 400, 110],
                        "mirror_role": "body",
                    },
                    {
                        "content": "This is the first paragraph.",
                        "level": "body",
                        "reading_order": 3,
                        "bbox": [50, 120, 500, 150],
                        "mirror_role": "body",
                    },
                    {
                        "content": "Page 1 of 3",
                        "level": "body",
                        "reading_order": 4,
                        "bbox": [450, 750, 520, 770],
                        "mirror_role": "footer",
                    },
                ],
            },
            {
                "page_number": 2,
                "texts": [
                    {
                        "content": "Company Report 2026",
                        "level": "body",
                        "reading_order": 1,
                        "bbox": [200, 20, 400, 40],
                        "mirror_role": "header",
                    },
                    {
                        "content": "Section 2: Methods",
                        "level": "h1",
                        "reading_order": 2,
                        "bbox": [50, 80, 400, 110],
                        "mirror_role": "body",
                    },
                    {
                        "content": "The methods are described below.",
                        "level": "body",
                        "reading_order": 3,
                        "bbox": [50, 120, 500, 150],
                        "mirror_role": "body",
                    },
                    {
                        "content": "Page 2 of 3",
                        "level": "body",
                        "reading_order": 4,
                        "bbox": [450, 750, 520, 770],
                        "mirror_role": "footer",
                    },
                ],
            },
        ],
        spec={
            "min_dfg_nodes": 4,  # 2 headers + 2 body (header/footer excluded from reading_flow)
            "require_reading_flow": True,
            "require_dfg_node_types": {"heading", "paragraph", "header", "footer"},
            "require_suppressed_noise_types": {"header", "footer"},
            "min_flows": 0,
        },
    ),
    # ── Cross-page paragraph ───────────────────────────────────────────────
    FixtureSpec(
        case_id="cross_page_paragraph",
        description="A paragraph that starts at the bottom of page 1 and continues on page 2",
        tier="ga_full",
        pages=[
            {
                "page_number": 1,
                "texts": [
                    {
                        "content": "This paragraph continues on the next page and does not end with punctuation",
                        "level": "body",
                        "reading_order": 1,
                        "bbox": [50, 600, 500, 640],
                        "mirror_role": "body",
                    },
                ],
            },
            {
                "page_number": 2,
                "texts": [
                    {
                        "content": "here is the rest of the sentence which completes the thought.",
                        "level": "body",
                        "reading_order": 1,
                        "bbox": [50, 80, 500, 120],
                        "mirror_role": "body",
                    },
                ],
            },
        ],
        spec={
            "min_dfg_nodes": 2,
            "require_reading_flow": True,
            "require_dfg_node_types": {"paragraph"},
            "min_flows": 1,
            "require_flow_types": {"cross_page_paragraph"},
        },
    ),
    # ── Cross-page table ───────────────────────────────────────────────────
    FixtureSpec(
        case_id="cross_page_table",
        description="A table spanning two pages with repeated headers on page 2",
        tier="ga_full",
        pages=[
            {
                "page_number": 1,
                "texts": [
                    {
                        "content": "Table 1: Revenue Summary",
                        "level": "body",
                        "reading_order": 1,
                        "bbox": [50, 100, 300, 130],
                        "mirror_role": "body",
                    },
                ],
                "tables": [
                    {
                        "table_id": "t1",
                        "headers": ["Year", "Revenue"],
                        "rows": [{"cells": [{"text": "2024", "confidence": 1.0}, {"text": "100M", "confidence": 1.0}]}],
                        "reading_order": 2,
                        "bbox": [50, 140, 500, 300],
                    },
                ],
            },
            {
                "page_number": 2,
                "tables": [
                    {
                        "table_id": "t2",
                        "headers": ["Year", "Revenue"],
                        "rows": [{"cells": [{"text": "2025", "confidence": 1.0}, {"text": "120M", "confidence": 1.0}]}],
                        "reading_order": 1,
                        "bbox": [50, 80, 500, 200],
                    },
                ],
            },
        ],
        spec={
            "min_dfg_nodes": 3,  # 1 text (table title) + 2 tables
            "require_reading_flow": True,
            "require_dfg_node_types": {"paragraph", "physical_table"},
            "min_flows": 1,
            "require_flow_types": {"cross_page_table"},
        },
    ),
    # ── Image node coverage ────────────────────────────────────────────────
    FixtureSpec(
        case_id="image_with_caption",
        description="A page with an image and its figure caption below",
        tier="ga_full",
        pages=[
            {
                "page_number": 1,
                "texts": [
                    {
                        "content": "Figure 1: System Architecture",
                        "level": "body",
                        "reading_order": 2,
                        "bbox": [50, 400, 500, 430],
                        "mirror_role": "body",
                    },
                ],
                "images": [
                    {
                        "image_id": "img_001",
                        "page": 1,
                        "bbox": [50, 100, 500, 380],
                        "caption": "Figure 1: System Architecture",
                        "reading_order": 1,
                        "file_type": "png",
                    },
                ],
            }
        ],
        spec={
            "min_dfg_nodes": 2,  # image + caption text
            "require_reading_flow": True,
            "require_dfg_node_types": {"image", "paragraph"},
            "require_relation_types": {"caption_of"},
            "min_outline_nodes": 0,
        },
    ),
    # ── Formula node coverage ──────────────────────────────────────────────
    FixtureSpec(
        case_id="formula_retention",
        description="A page with a mathematical formula rendered as LaTeX",
        tier="ga_full",
        pages=[
            {
                "page_number": 1,
                "texts": [
                    {
                        "content": "The energy equation is given by:",
                        "level": "body",
                        "reading_order": 1,
                        "bbox": [50, 100, 500, 130],
                        "mirror_role": "body",
                    },
                ],
                "formulas": [
                    {
                        "formula_id": "fm_001",
                        "page": 1,
                        "latex": "E=mc^{2}",
                        "raw": "E=mc2",
                        "bbox": [100, 150, 400, 190],
                        "reading_order": 2,
                        "source": "formula_zone",
                        "confidence": 0.95,
                    },
                ],
            }
        ],
        spec={
            "min_dfg_nodes": 2,  # text + formula
            "require_reading_flow": True,
            "require_dfg_node_types": {"paragraph", "formula"},
        },
    ),
    # ── Section tree ───────────────────────────────────────────────────────
    FixtureSpec(
        case_id="section_tree_hierarchy",
        description="A document with H1, H2 headings and body paragraphs forming a hierarchy",
        tier="ga_full",
        pages=[
            {
                "page_number": 1,
                "texts": [
                    {
                        "content": "Chapter 1: Overview",
                        "level": "h1",
                        "reading_order": 1,
                        "bbox": [50, 80, 400, 110],
                        "mirror_role": "body",
                        "confidence": 0.95,
                    },
                    {
                        "content": "This is body text under Chapter 1.",
                        "level": "body",
                        "reading_order": 2,
                        "bbox": [70, 120, 500, 150],
                        "mirror_role": "body",
                    },
                    {
                        "content": "1.1 Background",
                        "level": "h2",
                        "reading_order": 3,
                        "bbox": [70, 170, 400, 200],
                        "mirror_role": "body",
                        "confidence": 0.90,
                    },
                    {
                        "content": "More detailed background text.",
                        "level": "body",
                        "reading_order": 4,
                        "bbox": [90, 210, 500, 240],
                        "mirror_role": "body",
                    },
                ],
            }
        ],
        spec={
            "min_dfg_nodes": 4,
            "require_reading_flow": True,
            "require_dfg_node_types": {"heading", "paragraph"},
            "min_outline_nodes": 2,
        },
    ),
    # ── Noise policy — forensic profile ────────────────────────────────────
    FixtureSpec(
        case_id="noise_forensic_profile",
        description="Same header/footer fixture but verified under forensic profile (noise preserved)",
        tier="forensic",
        pages=[
            {
                "page_number": 1,
                "texts": [
                    {
                        "content": "CONFIDENTIAL",
                        "level": "body",
                        "reading_order": 1,
                        "bbox": [200, 10, 350, 30],
                        "mirror_role": "header",
                    },
                    {
                        "content": "Body text here.",
                        "level": "body",
                        "reading_order": 2,
                        "bbox": [50, 80, 500, 110],
                        "mirror_role": "body",
                    },
                    {
                        "content": "Page 1",
                        "level": "body",
                        "reading_order": 3,
                        "bbox": [450, 750, 520, 770],
                        "mirror_role": "footer",
                    },
                ],
            },
            {
                "page_number": 2,
                "texts": [
                    {
                        "content": "CONFIDENTIAL",
                        "level": "body",
                        "reading_order": 1,
                        "bbox": [200, 10, 350, 30],
                        "mirror_role": "header",
                    },
                    {
                        "content": "More body text.",
                        "level": "body",
                        "reading_order": 2,
                        "bbox": [50, 80, 500, 110],
                        "mirror_role": "body",
                    },
                    {
                        "content": "Page 2",
                        "level": "body",
                        "reading_order": 3,
                        "bbox": [450, 750, 520, 770],
                        "mirror_role": "footer",
                    },
                ],
            },
        ],
        spec={
            "min_dfg_nodes": 4,
            "require_reading_flow": True,
            "require_dfg_node_types": {"header", "footer", "paragraph"},
        },
    ),
]
