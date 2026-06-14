# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Page-level extraction facade — handlers in ``pipeline/handlers/`` (CPA design 12)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from docmirror.models.entities.domain import Block, PageLayout, Style, TextSpan
from docmirror.core.pipeline.context import PageExtractionContext
from docmirror.core.pipeline.handlers import scanned_page as scanned_page_mod
from docmirror.core.pipeline.handlers import fallback_table as fallback_table_mod
from docmirror.core.pipeline.handlers import formula_zone as formula_zone_mod
from docmirror.core.pipeline.handlers import model_segmentation as model_segmentation_mod
from docmirror.core.pipeline.handlers import page_images as page_images_mod
from docmirror.core.pipeline.handlers import page_styles as page_styles_mod
from docmirror.core.pipeline.handlers import table_zone as table_zone_mod
from docmirror.core.pipeline.handlers import text_zone as text_zone_mod
from docmirror.core.pipeline.handlers import zone_utils as zone_utils_mod

if TYPE_CHECKING:
    from docmirror.core.extraction.extractor import CoreExtractor


class PageExtractor:
    """Single-page zone → block extraction (delegates to ``pipeline/handlers/*``)."""

    def __init__(self, host: "CoreExtractor") -> None:
        self._host = host

    def extract_scanned_page(self, **kwargs) -> PageLayout:
        return scanned_page_mod.extract_scanned_page(self, **kwargs)

    @staticmethod
    def _group_words_into_lines(words, tolerance_ratio: float = 0.5):
        return zone_utils_mod.group_words_into_lines(words, tolerance_ratio)

    def _handle_formula_zone(self, *args, **kwargs):
        return formula_zone_mod.handle_formula_zone(self, *args, **kwargs)

    def _handle_data_table_zone(self, *args, **kwargs):
        return table_zone_mod.handle_data_table_zone(self, *args, **kwargs)

    def _handle_text_zone(self, *args, **kwargs):
        return text_zone_mod.handle_text_zone(self, *args, **kwargs)

    def _extract_page_images(self, *args, **kwargs):
        return page_images_mod.extract_page_images(self, *args, **kwargs)

    def _fallback_table_extraction(self, *args, **kwargs):
        return fallback_table_mod.fallback_table_extraction(self, *args, **kwargs)

    def run(self, ctx: PageExtractionContext):
        from docmirror.core.pipeline.page_pipeline import PagePipeline

        return PagePipeline(self._host).run(ctx)

    def _model_segmentation(self, fitz_page, page_plum, page_idx: int):
        return model_segmentation_mod.model_segmentation(self, fitz_page, page_plum, page_idx)

    def _crop_zone_image(self, fitz_page, bbox) -> bytes:
        return zone_utils_mod.crop_zone_image(fitz_page, bbox)

    def _recognize_formula(self, image_bytes: bytes) -> str:
        return zone_utils_mod.recognize_formula(self, image_bytes)

    def _extract_page_styles(self, fitz_page) -> dict[str, Style]:
        return page_styles_mod.extract_page_styles(self, fitz_page)

    def _build_spans(self, text, bbox, style_map) -> tuple[TextSpan, ...]:
        return page_styles_mod.build_spans(text, bbox, style_map)

    def _infer_heading_level(self, text, style_map) -> int | None:
        return page_styles_mod.infer_heading_level(text, style_map)


__all__ = ["PageExtractor"]
