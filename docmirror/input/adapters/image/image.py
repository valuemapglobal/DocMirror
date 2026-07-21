# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Image Adapter — Image → ParseResult
====================================

Converts image files (JPG, PNG, TIFF, etc.) into OCR text blocks.  The adapter
keeps line-level bounding boxes so downstream vNext evidence, domain solvers,
and local repair can trace fields back to image regions.
"""

from __future__ import annotations

import logging
from pathlib import Path

from docmirror.framework.base import BaseParser

logger = logging.getLogger(__name__)


class ImageAdapter(BaseParser):
    """
    Image format adapter using OCR extraction.

    Produces line-level TextBlocks with image-space bounding boxes when the OCR
    backend exposes coordinates.
    """

    async def to_parse_result(self, file_path: Path, **kwargs) -> ParseResult:
        """
        Convert an image file to ParseResult using OCR.
        """
        from docmirror.models.entities.parse_result import (
            ExtractionMethod,
            PageContent,
            ParseResult,
            ParserInfo,
        )

        logger.info(f"[ImageAdapter] Starting image parsing for: {file_path}")
        ocr_mode = str(kwargs.get("ocr_mode") or "auto").lower()
        texts, width, height = ([], None, None) if ocr_mode == "off" else await self._extract_text_blocks(file_path)
        logger.info(f"[ImageAdapter] Completed image parsing for: {file_path}")

        page = PageContent(page_number=1, texts=texts, width=width, height=height, page_mode="scanned_ocr")

        return ParseResult(
            pages=[page],
            parser_info=ParserInfo(
                parser_name="ImageAdapter",
                page_count=1,
                extraction_method=ExtractionMethod.OCR,
                overall_confidence=0.8,
            ),
        )

    async def _extract_text_blocks(self, file_path: Path) -> tuple[list[TextBlock], int | None, int | None]:
        """Extract OCR text blocks from the image."""
        import cv2

        from docmirror.models.entities.parse_result import TextBlock, TextLevel

        logger.debug(f"[ImageAdapter] Reading image file: {file_path}")
        img = cv2.imread(str(file_path))
        if img is None:
            logger.error(f"[ImageAdapter] Failed to read image: {file_path.name}")
            return [], None, None
        height, width = int(img.shape[0]), int(img.shape[1])
        blocks = self._extract_text_blocks_from_image(img, file_path)
        if not blocks:
            text = self._extract_text_from_image(img, file_path)
            blocks = [TextBlock(content=text, level=TextLevel.BODY)] if text else []
        return blocks, width, height

    def _extract_text_from_image(self, img, _file_path: Path) -> str:
        """Use built-in or external OCR depending on image quality."""
        return "\n".join(
            block.content for block in self._extract_text_blocks_from_image(img, _file_path) if block.content
        )

    def _extract_text_blocks_from_image(self, img, _file_path: Path) -> list[TextBlock]:
        """Use built-in or external OCR and preserve line bboxes when available."""
        from docmirror.configs.runtime.settings import default_settings
        from docmirror.ocr.fallback import (
            _resolve_external_ocr_provider,
            assess_image_quality_from_bgr,
        )

        threshold = getattr(default_settings, "external_ocr_quality_threshold", None)
        provider = _resolve_external_ocr_provider(getattr(default_settings, "external_ocr_provider", None))
        quality = assess_image_quality_from_bgr(img)
        logger.debug(
            "[ImageAdapter] OCR route: quality=%s, threshold=%s, external_provider=%s → %s",
            quality,
            threshold,
            "set" if provider is not None else "unset",
            "external" if (threshold is not None and provider is not None and quality < threshold) else "builtin",
        )
        if threshold is not None and provider is not None and quality < threshold:
            try:
                out = provider(img, page_idx=0, dpi=200)
            except Exception as e:
                logger.warning(f"[ImageAdapter] External OCR failed: {e}")
                out = None
            if out is not None:
                logger.info(f"[ImageAdapter] Delegated to external OCR (quality={quality})")
                return self._blocks_from_ocr_result(out)
        try:
            from docmirror.ocr.vision.rapidocr_engine import get_ocr_engine

            engine = get_ocr_engine()
            words = engine.detect_image_words(img)
            return self._blocks_from_words(words)
        except Exception as e:
            logger.warning(f"[ImageAdapter] OCR fallback failed: {e}")
            return []

    @staticmethod
    def _text_from_ocr_result(out) -> str:
        """Convert external OCR result (list of words or dict) to plain text."""
        return "\n".join(block.content for block in ImageAdapter._blocks_from_ocr_result(out) if block.content)

    @staticmethod
    def _blocks_from_ocr_result(out) -> list[TextBlock]:
        """Convert external OCR result (list of words or dict) to TextBlocks."""
        from docmirror.models.entities.parse_result import TextBlock, TextLevel

        if isinstance(out, list):
            return ImageAdapter._blocks_from_words(out)
        if isinstance(out, dict):
            lines = out.get("lines", [])
            if lines:
                blocks: list[TextBlock] = []
                for line in lines:
                    if isinstance(line, dict):
                        text = str(line.get("text") or "").strip()
                        bbox = _bbox(line.get("bbox"))
                        confidence = _confidence(line.get("confidence"), default=0.8)
                    else:
                        text = str(line).strip()
                        bbox = None
                        confidence = 0.8
                    if text:
                        evidence_ids = (
                            [str(item) for item in line.get("evidence_ids") or []] if isinstance(line, dict) else []
                        )
                        blocks.append(
                            TextBlock(
                                content=text,
                                level=TextLevel.BODY,
                                bbox=bbox,
                                confidence=confidence,
                                evidence_ids=evidence_ids,
                            )
                        )
                return blocks
            header = out.get("header_text", "").strip()
            footer = out.get("footer_text", "").strip()
            table = out.get("table", [])
            parts = [header] if header else []
            if table:
                for row in table:
                    if isinstance(row, (list, tuple)):
                        parts.append(" | ".join(str(c) for c in row if c))
                    else:
                        parts.append(str(row))
            if footer:
                parts.append(footer)
            text = "\n".join(parts) if parts else ""
            return [TextBlock(content=text, level=TextLevel.BODY)] if text else []
        return []

    @staticmethod
    def _blocks_from_words(words) -> list[TextBlock]:
        """Group OCR words/blocks into line TextBlocks."""
        from docmirror.models.entities.parse_result import TextBlock, TextLevel

        if not words:
            return []
        normalized = []
        for word_index, word in enumerate(words):
            if len(word) < 5:
                continue
            text = str(word[4] or "").strip()
            if not text:
                continue
            bbox = _bbox(word[:4])
            if not bbox:
                continue
            confidence = _confidence(word[8] if len(word) > 8 else word[5] if len(word) > 5 else 0.8)
            evidence_id = f"ocr:p0:w{word_index:06d}"
            normalized.append((*bbox, text, confidence, evidence_id))
        if not normalized:
            return []
        heights = sorted(max(1.0, item[3] - item[1]) for item in normalized)
        median_height = heights[len(heights) // 2]
        y_tolerance = max(8.0, median_height * 0.65)

        lines: list[list[tuple[float, float, float, float, str, float, str]]] = []
        current: list[tuple[float, float, float, float, str, float, str]] = []
        current_y = 0.0
        for item in sorted(normalized, key=lambda value: (((value[1] + value[3]) / 2.0), value[0])):
            center_y = (item[1] + item[3]) / 2.0
            if current and abs(center_y - current_y) > y_tolerance:
                lines.append(current)
                current = []
            current.append(item)
            current_y = sum((line_item[1] + line_item[3]) / 2.0 for line_item in current) / len(current)
        if current:
            lines.append(current)

        blocks: list[TextBlock] = []
        for line in lines:
            ordered = sorted(line, key=lambda item: item[0])
            text = " ".join(item[4] for item in ordered).strip()
            if not text:
                continue
            bbox = [
                min(item[0] for item in ordered),
                min(item[1] for item in ordered),
                max(item[2] for item in ordered),
                max(item[3] for item in ordered),
            ]
            confidence = sum(item[5] for item in ordered) / len(ordered)
            tokens = [
                {
                    "evidence_id": item[6],
                    "text": item[4],
                    "bbox": [item[0], item[1], item[2], item[3]],
                    "confidence": item[5],
                }
                for item in ordered
            ]
            blocks.append(
                TextBlock(
                    content=text,
                    level=TextLevel.BODY,
                    bbox=bbox,
                    confidence=confidence,
                    evidence_ids=[item[6] for item in ordered],
                    slm_entities={"ocr_tokens": tokens},
                )
            )
        return blocks


def _bbox(value) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    try:
        x0, y0, x1, y1 = [float(value[idx]) for idx in range(4)]
    except (TypeError, ValueError):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return [x0, y0, x1, y1]


def _confidence(value, *, default: float = 0.8) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
