# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Page images handler — extracts embedded and rendered page images.

Purpose: Collects image blocks (figures, stamps, logos) with bboxes for
inclusion in ``PageLayout``.

Main components: ``extract_page_images``.

Upstream: ``PageExtractor`` / assemble stage for image zones.

Downstream: ``physical.models.Block`` (image type).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from docmirror.models.entities.domain import Block

if TYPE_CHECKING:
    from docmirror.core.pipeline.page_extractor import PageExtractor

logger = logging.getLogger(__name__)


def extract_page_images(
    _extractor: PageExtractor,
    fitz_page,
    fitz_doc,
    page_idx: int,
    blocks: list[Block],
    reading_order: int,
) -> tuple[list[Block], int]:
    """Extract images from a page and create image blocks.

    Returns:
        (new_blocks, updated_reading_order)
    """
    new_blocks: list[Block] = []
    try:
        for img_info in fitz_page.get_images(full=True):
            xref = img_info[0]
            try:
                img_data = fitz_doc.extract_image(xref)
                if not img_data or not img_data.get("image"):
                    continue
                img_bytes = img_data["image"]
                img_rects = fitz_page.get_image_rects(xref)
                if not img_rects:
                    continue
                img_rect = img_rects[0]
                img_bbox = (img_rect.x0, img_rect.y0, img_rect.x1, img_rect.y1)

                if (img_rect.x1 - img_rect.x0) < 50 or (img_rect.y1 - img_rect.y0) < 50:
                    continue

                caption = None
                caption_y_range = (img_rect.y1, img_rect.y1 + 30)
                for existing_block in blocks:
                    if existing_block.block_type == "text" and existing_block.raw_content:
                        bx0, by0, bx1, by1 = existing_block.bbox
                        if caption_y_range[0] <= by0 <= caption_y_range[1] and bx0 < img_rect.x1 and bx1 > img_rect.x0:
                            caption = existing_block.raw_content
                            break

                img_id = f"blk_{page_idx}_{reading_order}"
                new_blocks.append(
                    Block(
                        block_id=img_id,
                        block_type="image",
                        bbox=img_bbox,
                        reading_order=reading_order,
                        page=page_idx + 1,
                        raw_content=img_bytes,
                        caption=caption,
                    )
                )
                reading_order += 1
            except Exception as exc:
                logger.debug(f"image extraction: suppressed {exc}")
                continue
    except Exception as e:
        logger.debug(f"[DocMirror] image extraction skip: {e}")
    return new_blocks, reading_order
