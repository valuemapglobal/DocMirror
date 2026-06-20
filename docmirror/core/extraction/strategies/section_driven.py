# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Section-driven extraction strategy — header/section tree parsing.

Purpose: Builds a section tree from detected headings and extracts content
block-by-block for documents with strong hierarchical structure (reports,
policies).

Main components: ``SectionDrivenStrategy``.

Upstream: ``strategy_registry`` selection, ``PreAnalysisResult``.

Downstream: ``BaseResult`` blocks via ``CoreExtractor`` strategy path.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any

from .strategy_registry import BaseExtractionStrategy, register_strategy

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Section Header Patterns (multi-language)
# ═══════════════════════════════════════════════════════════════════════════════

# L1 chapter headers (Chinese numerals, 第N章, Section/Chapter/Part N)
L1_PATTERNS = [
    re.compile(r"^(一|二|三|四|五|六|七|八|九|十)\s{1,4}[\u4e00-\u9fff]"),
    re.compile(r"^第[一二三四五六七八九十百]+[章部分篇]"),
    re.compile(r"^(Section|Chapter|Part)\s+\d+", re.IGNORECASE),
]

# L2 sub-section headers (parenthetical numerals, 第N节, dotted outlines)
L2_PATTERNS = [
    re.compile(r"^[（(](一|二|三|四|五|六|七|八|九|十)[）)]"),
    re.compile(r"^第[一二三四五六七八九十百]+[节条款]"),
    re.compile(r"^\d+\.\d+\s+[\u4e00-\u9fffA-Z]"),
]

# Level 3: Numbered items within sections (e.g. "账户1（", "Item 1:")
L3_PATTERNS = [
    re.compile(r"^账户\d+[（(]"),
    re.compile(r"^授信协议\s*\d+"),
    re.compile(r"^(Item|Record)\s+\d+", re.IGNORECASE),
]


# ═══════════════════════════════════════════════════════════════════════════════
# Watermark & Noise Filtering
# ═══════════════════════════════════════════════════════════════════════════════

# Common watermark patterns in Chinese financial/government documents
_WATERMARK_PATTERNS = [
    # "姓名 2026-03-04 10:00:07" (name + full datetime stamp)
    re.compile(r"^[\u4e00-\u9fff]{2,4}\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}$"),
    # "姓名 2026-03-04" (name + date only)
    re.compile(r"^[\u4e00-\u9fff]{2,4}\s+\d{4}-\d{2}-\d{2}$"),
    # Truncated watermark at page edge: "姓名 20"
    re.compile(r"^[\u4e00-\u9fff]{2,4}\s+\d{2}$"),
]

# Threshold for repeated-line stamp detection (e.g. company name repeated 3+ times)
_STAMP_REPEAT_THRESHOLD = 3


def _is_watermark_line(line: str) -> bool:
    """Check if a line matches known watermark patterns."""
    for pat in _WATERMARK_PATTERNS:
        if pat.match(line):
            return True
    return False


def _filter_noise(lines: list[str]) -> list[str]:
    """Remove watermarks and repeated company stamps from text lines."""
    # Pass 1: Remove known watermark patterns
    clean = [line for line in lines if not _is_watermark_line(line)]
    if not clean:
        return clean

    # Pass 2: Remove consecutive repeated lines (company stamps)
    result: list[str] = []
    i = 0
    while i < len(clean):
        # Count consecutive identical lines
        j = i + 1
        while j < len(clean) and clean[j] == clean[i]:
            j += 1
        repeat_count = j - i

        if repeat_count >= _STAMP_REPEAT_THRESHOLD:
            # Skip all repeated stamp lines
            i = j
        else:
            result.append(clean[i])
            i += 1

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Section Scanner
# ═══════════════════════════════════════════════════════════════════════════════


def _match_header_level(line: str) -> int | None:
    """
    Match a line against section header patterns.

    Returns:
        1, 2, or 3 for the matched level, or None if no match.
    """
    for pat in L1_PATTERNS:
        if pat.match(line):
            return 1
    for pat in L2_PATTERNS:
        if pat.match(line):
            return 2
    for pat in L3_PATTERNS:
        if pat.match(line):
            return 3
    return None


def _scan_sections(fitz_doc: Any) -> list[dict]:
    """
    Scan entire document text layer → build flat section list.

    Each section dict:
        level: int (0=doc title, 1=chapter, 2=sub-section, 3=item)
        title: str
        page_start: int (1-indexed)
        content_lines: list[str]
    """
    # Collect clean text per page
    page_texts: list[tuple[int, list[str]]] = []
    for page_idx in range(len(fitz_doc)):
        raw_text = fitz_doc[page_idx].get_text()
        raw_lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
        clean_lines = _filter_noise(raw_lines)
        page_texts.append((page_idx, clean_lines))

    # Flatten into a stream with page tracking
    stream: list[tuple[int, str]] = []  # (page_idx, line_text)
    for page_idx, lines in page_texts:
        for line in lines:
            stream.append((page_idx, line))

    # Scan for section headers
    sections: list[dict] = []
    current: dict | None = None

    for page_idx, line in stream:
        level = _match_header_level(line)

        if level is not None:
            # Save previous section
            if current is not None:
                sections.append(current)

            current = {
                "level": level,
                "title": line,
                "page_start": page_idx + 1,  # 1-indexed
                "content_lines": [],
            }
        elif current is not None:
            current["content_lines"].append(line)
        else:
            # Content before any section header (document title area)
            current = {
                "level": 0,
                "title": line if "报告" in line or "Report" in line else "文档头部",
                "page_start": page_idx + 1,
                "content_lines": [] if ("报告" in line or "Report" in line) else [line],
            }

    # Don't forget the last section
    if current is not None:
        sections.append(current)

    return sections


# ═══════════════════════════════════════════════════════════════════════════════
# Section Tree Builder
# ═══════════════════════════════════════════════════════════════════════════════


def _build_section_tree(sections: list[dict]) -> list[dict]:
    """
    Build a flat section index (preserving hierarchy via level + parent_id).

    Each entry:
        id: str ("1", "1.1", "1.1.1")
        level: int
        title: str
        page_start: int
        line_count: int
    """
    tree: list[dict] = []
    counters = [0, 0, 0, 0]  # L0, L1, L2, L3

    for sec in sections:
        level = sec["level"]
        lines = sec["content_lines"]

        # Update counters
        if level <= 0:
            counters[0] += 1
            sec_id = str(counters[0])
        elif level == 1:
            counters[1] += 1
            counters[2] = 0
            counters[3] = 0
            sec_id = str(counters[1])
        elif level == 2:
            counters[2] += 1
            counters[3] = 0
            sec_id = f"{counters[1]}.{counters[2]}"
        else:
            counters[3] += 1
            sec_id = f"{counters[1]}.{counters[2]}.{counters[3]}"

        tree.append(
            {
                "id": sec_id,
                "level": level,
                "title": sec["title"],
                "page_start": sec["page_start"],
                "line_count": len(lines),
            }
        )

    return tree


# ═══════════════════════════════════════════════════════════════════════════════
# Block Assembly
# ═══════════════════════════════════════════════════════════════════════════════

_EMPTY_PLACEHOLDERS = frozenset({"- -", "--", "-"})


def _is_empty_section(lines: list[str]) -> bool:
    """Check if a section contains only empty placeholders."""
    return len(lines) > 0 and all(line in _EMPTY_PLACEHOLDERS for line in lines)


def _sections_to_pages(sections: list[dict], total_pages: int) -> tuple[list, str]:
    """
    Convert sections into PageLayout objects and full_text.

    Returns:
        (pages, full_text) — pages is a list of PageLayout, full_text is
        the concatenated document text.
    """
    from docmirror.models.entities.domain import Block, PageLayout

    # Group sections by page
    page_sections: dict[int, list[dict]] = {}
    for sec in sections:
        pn = sec["page_start"]
        page_sections.setdefault(pn, []).append(sec)

    pages: list[PageLayout] = []
    full_text_parts: list[str] = []
    reading_order = 0

    for page_num in range(1, total_pages + 1):
        secs = page_sections.get(page_num, [])
        blocks: list[Block] = []

        for sec in secs:
            content = "\n".join(sec["content_lines"])
            is_empty = _is_empty_section(sec["content_lines"])

            # Determine block type
            if sec["level"] == 0:
                block_type = "title"
            elif is_empty:
                # Empty placeholder sections — still record as text for completeness
                block_type = "text"
                content = f"{sec['title']}\n（无数据）"
            else:
                block_type = "text"

            # Build the title block
            title_block = Block._fast(
                block_id=str(uuid.uuid4())[:8],
                block_type="title" if sec["level"] <= 1 else "text",
                raw_content=sec["title"],
                reading_order=reading_order,
                page=page_num,
                heading_level=sec["level"] if sec["level"] >= 1 else 1,
            )
            blocks.append(title_block)
            reading_order += 1
            full_text_parts.append(sec["title"])

            # Build the content block (if has content)
            if sec["content_lines"] and not is_empty:
                content_block = Block._fast(
                    block_id=str(uuid.uuid4())[:8],
                    block_type=block_type,
                    raw_content=content,
                    reading_order=reading_order,
                    page=page_num,
                )
                blocks.append(content_block)
                reading_order += 1
                full_text_parts.append(content)

        page_layout = PageLayout(
            page_number=page_num,
            blocks=tuple(blocks),
            is_scanned=False,
        )
        pages.append(page_layout)

    full_text = "\n\n".join(full_text_parts)
    return pages, full_text


def _fitz_raw_full_text(fitz_doc: Any) -> str:
    """Concatenate all page text layers (for SDU enrich — Phase 3)."""
    parts: list[str] = []
    for idx in range(len(fitz_doc)):
        parts.append(fitz_doc[idx].get_text())
    return "\n\n".join(parts)


def _enrich_pages_with_pipe_tables(pages: list, detect_text: str) -> tuple[list, bool]:
    """Add pipe grid table blocks when embedded in section-led documents (Phase 3)."""
    from docmirror.core.analyze.sso_config import pipe_grid_enrich_threshold
    from docmirror.core.geometry.table_attrs import build_table_geometry_attrs
    from docmirror.core.table.structure_detect import build_pipe_table_from_text, detect_pipe_grid_in_text
    from docmirror.models.entities.domain import Block, PageLayout

    threshold = pipe_grid_enrich_threshold()
    signal = detect_pipe_grid_in_text(detect_text)
    if signal.confidence < threshold:
        return pages, False

    built = build_pipe_table_from_text(detect_text)
    if not built or not built[0]:
        return pages, False

    table = built[0]
    target_page = 1
    max_reading = -1
    for page in pages:
        if page.blocks:
            ro = max(b.reading_order for b in page.blocks)
            if ro > max_reading:
                max_reading = ro
                target_page = page.page_number

    enriched_pages: list = []
    did_enrich = False
    for page in pages:
        if page.page_number != target_page:
            enriched_pages.append(page)
            continue
        reading_order = max((b.reading_order for b in page.blocks), default=-1) + 1
        page_width = float(getattr(page, "width", 0.0) or 0.0)
        page_height = float(getattr(page, "height", 0.0) or 0.0)
        table_width = page_width if page_width > 0 else max((len(r) for r in table), default=1) * 100.0
        table_height = page_height if page_height > 0 else max(len(table), 1) * 24.0
        table_bbox = (0.0, 0.0, table_width, table_height)
        attrs = build_table_geometry_attrs(
            table,
            table_bbox=table_bbox,
            page_number=page.page_number,
            table_index=0,
            geometry_source="section_pipe_table_estimated",
            geometry_confidence=signal.confidence,
            base_attrs={
                "extraction_layer": "section_pipe_table",
                "extraction_confidence": signal.confidence,
                "zone_type": "section_pipe_table",
            },
        )
        table_block = Block._fast(
            block_id=str(uuid.uuid4())[:8],
            block_type="table",
            raw_content=table,
            bbox=table_bbox,
            reading_order=reading_order,
            page=page.page_number,
            attrs=attrs,
        )
        new_blocks = tuple(list(page.blocks) + [table_block])
        enriched_pages.append(
            PageLayout(
                page_number=page.page_number,
                width=getattr(page, "width", 0.0),
                height=getattr(page, "height", 0.0),
                blocks=new_blocks,
                semantic_zones=getattr(page, "semantic_zones", {}),
                is_scanned=getattr(page, "is_scanned", False),
            )
        )
        did_enrich = True

    return enriched_pages, did_enrich


# ═══════════════════════════════════════════════════════════════════════════════
# Strategy Implementation
# ═══════════════════════════════════════════════════════════════════════════════


@register_strategy("section_dominant")
class SectionDrivenStrategy(BaseExtractionStrategy):
    """
    Generic extraction strategy for section-dominant documents.

    Applicable to any document organized by hierarchical numbered sections:
    credit reports, audit reports, evaluation reports, legal/regulatory
    documents, and similar structured documents.

    Detection: PreAnalyzer counts section headers in sampled pages.
    If >= 3 headers found → content_type = "section_dominant" → this strategy.
    """

    def extract(self, fitz_doc: Any, _pre_analysis: Any) -> tuple:
        """
        Section-header-driven extraction.

        Returns:
            Standard 6-tuple: (pages, full_text, layer, confidence, perf, page_perf)
        """
        t0 = time.perf_counter()
        _perf: dict[str, float] = {}

        # Step 1: Scan section headers → build structure tree
        _t = time.perf_counter()
        sections = _scan_sections(fitz_doc)
        _perf["section_scan_ms"] = (time.perf_counter() - _t) * 1000

        logger.info(
            f"[SectionDrivenStrategy] Scanned {len(sections)} sections "
            f"in {_perf['section_scan_ms']:.0f}ms "
            f"(L1={sum(1 for s in sections if s['level'] == 1)}, "
            f"L2={sum(1 for s in sections if s['level'] == 2)}, "
            f"L3={sum(1 for s in sections if s['level'] == 3)})"
        )

        # Step 2: Build section tree (for metadata)
        _t = time.perf_counter()
        section_tree = _build_section_tree(sections)
        _perf["tree_build_ms"] = (time.perf_counter() - _t) * 1000

        # Step 3: Convert sections → PageLayout/Block → standard output
        _t = time.perf_counter()
        total_pages = len(fitz_doc)
        pages, full_text = _sections_to_pages(sections, total_pages)
        raw_full_text = _fitz_raw_full_text(fitz_doc)
        pages, pipe_enriched = _enrich_pages_with_pipe_tables(pages, raw_full_text)
        if pipe_enriched:
            _perf["pipe_table_enrich"] = True
        _perf["block_assembly_ms"] = (time.perf_counter() - _t) * 1000

        # Step 4: Assemble result
        _perf["total_ms"] = (time.perf_counter() - t0) * 1000
        extraction_layer = "section_driven"
        extraction_confidence = 0.95  # high confidence for template-matched documents
        _page_perf: list = []  # no per-page breakdown needed

        # Store section tree for metadata injection by extractor
        _perf["_section_tree"] = section_tree  # piggyback on perf dict

        total_blocks = sum(len(p.blocks) for p in pages)
        logger.info(
            f"[SectionDrivenStrategy] ◀ Complete | "
            f"sections={len(sections)} | pages={len(pages)} | "
            f"blocks={total_blocks} | elapsed={_perf['total_ms']:.0f}ms"
        )

        return pages, full_text, extraction_layer, extraction_confidence, _perf, _page_perf
