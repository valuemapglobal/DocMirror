# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Table structure fixes applied after cross-page merge in PDF processing."""

from __future__ import annotations

import logging

from docmirror.models.entities.domain import Block, PageLayout

logger = logging.getLogger(__name__)


def fix_table_structures(pages: list) -> list:
    """Apply table structure fix to all table blocks after cross-page merge."""
    from docmirror.core.table.table_structure_fix import fix_table_structure

    fixed_pages = []
    for pg in pages:
        new_blocks = []
        for block in pg.blocks:
            if block.block_type == "table" and isinstance(block.raw_content, list) and len(block.raw_content) >= 2:
                fixed = fix_table_structure(block.raw_content)
                new_blocks.append(
                    Block(
                        block_id=block.block_id,
                        block_type=block.block_type,
                        bbox=block.bbox,
                        reading_order=block.reading_order,
                        page=block.page,
                        raw_content=fixed,
                        attrs=block.attrs,
                        evidence_ids=block.evidence_ids,
                    )
                )
            else:
                new_blocks.append(block)
        fixed_pages.append(
            PageLayout(
                page_number=pg.page_number,
                width=pg.width,
                height=pg.height,
                blocks=tuple(new_blocks),
                semantic_zones=pg.semantic_zones,
                is_scanned=pg.is_scanned,
            )
        )
    return fixed_pages


def infer_missing_headers(pages: list) -> list:
    """Infer and prepend missing table headers from earlier text blocks."""
    from docmirror.core.utils.vocabulary import _is_header_row, _score_header_by_vocabulary

    for pg in pages:
        for block in pg.blocks:
            if block.block_type != "table" or not isinstance(block.raw_content, list):
                continue
            rc = block.raw_content
            if not rc or len(rc) < 2:
                continue
            if _is_header_row(rc[0]):
                continue

            logger.warning(
                "[Extractor] Page %s: Table block missing header, searching for header in text...",
                pg.page_number,
            )
            candidate_header = None
            best_vocab = 0
            for prev_pg in pages:
                if prev_pg.page_number > pg.page_number:
                    break
                for tb in prev_pg.blocks:
                    if tb.block_type == "text" and isinstance(tb.raw_content, str):
                        words = [w.strip() for w in tb.raw_content.split() if w.strip()]
                        if len(words) >= 3:
                            vs = _score_header_by_vocabulary(words)
                            if vs > best_vocab and vs >= 3:
                                best_vocab = vs
                                candidate_header = words
            if candidate_header:
                logger.info(
                    "[Merger] Page %s: Prepending inferred header (vocabulary score: %s)",
                    pg.page_number,
                    best_vocab,
                )
                ncols = len(rc[0])
                if len(candidate_header) == ncols:
                    aligned = candidate_header
                elif len(candidate_header) > ncols:
                    aligned = candidate_header[:ncols]
                else:
                    aligned = candidate_header + [""] * (ncols - len(candidate_header))
                rc_new = [aligned] + list(rc)
                new_blocks = []
                for b in pg.blocks:
                    if b is block:
                        new_blocks.append(
                            Block(
                                block_id=b.block_id,
                                block_type=b.block_type,
                                bbox=b.bbox,
                                reading_order=b.reading_order,
                                page=b.page,
                                raw_content=rc_new,
                                attrs=b.attrs,
                                evidence_ids=b.evidence_ids,
                            )
                        )
                    else:
                        new_blocks.append(b)
                idx = pages.index(pg)
                pages[idx] = PageLayout(
                    page_number=pg.page_number,
                    width=pg.width,
                    height=pg.height,
                    blocks=tuple(new_blocks),
                    semantic_zones=pg.semantic_zones,
                    is_scanned=pg.is_scanned,
                )
                logger.info(
                    "[DocMirror] header inferred from text: vocab=%s, words=%s",
                    best_vocab,
                    len(candidate_header),
                )
                break
    return pages
