# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Image Adapter — Image → BaseResult
====================================

Converts image files (JPG, PNG, TIFF, etc.) into structured data using 
RapidOCR (ONNX Runtime) for plain text extraction. This adapter produces a single 
text Block without complex structured table/entity data, as it currently operates
in a purely CPU-bound environment without Vision-Language Models.
"""
from __future__ import annotations


import logging
from pathlib import Path

from docmirror.framework.base import BaseParser
from docmirror.models.entities.domain import BaseResult, Block, PageLayout

logger = logging.getLogger(__name__)


class ImageAdapter(BaseParser):
    """
    Image format adapter using OCR extraction.
    
    Produces a single text Block containing all recognized text lines joined by newlines.
    """

    async def to_base_result(self, file_path: Path) -> BaseResult:
        """
        Convert an image file to BaseResult using OCR.
        """
        logger.info(f"[ImageAdapter] Starting image parsing for: {file_path}")
        result = await self._ocr_fallback(file_path)
        logger.info(f"[ImageAdapter] Completed image parsing for: {file_path}")
        return result

    async def _ocr_fallback(self, file_path: Path) -> BaseResult:
        """
        Extract text from the image. When image quality is below
        ``external_ocr_quality_threshold`` and ``external_ocr_provider``
        is set, delegates to the external provider; otherwise uses RapidOCR.

        Returns a BaseResult with a single text Block containing all
        recognized text lines joined by newlines.
        """
        import cv2
        logger.debug(f"[ImageAdapter] Reading image file: {file_path}")
        img = cv2.imread(str(file_path))
        if img is None:
            logger.error(f"[ImageAdapter] Failed to read image, cv2.imread returned None: {file_path.name}")
            text = ""
        else:
            text = self._extract_text_from_image(img, file_path)
        
        blocks = [Block(block_type="text", raw_content=text, page=0)] if text else []
        page = PageLayout(page_number=0, blocks=tuple(blocks))
        return BaseResult(pages=(page,), full_text=text, metadata={"source_format": "image_ocr"})

    def _extract_text_from_image(self, img, file_path: Path) -> str:
        """Use built-in or external OCR depending on image quality."""
        from docmirror.configs.settings import default_settings
        from docmirror.core.ocr.fallback import (
            _resolve_external_ocr_provider,
            assess_image_quality_from_bgr,
        )
        threshold = getattr(default_settings, "external_ocr_quality_threshold", None)
        provider = _resolve_external_ocr_provider(
            getattr(default_settings, "external_ocr_provider", None)
        )
        quality = assess_image_quality_from_bgr(img)
        logger.debug(
            "[ImageAdapter] OCR route: quality=%s, threshold=%s, external_provider=%s → %s",
            quality,
            threshold,
            "set" if provider is not None else "unset",
            "external" if (threshold is not None and provider is not None and quality < threshold) else "builtin",
        )
        if (
            threshold is not None
            and provider is not None
            and quality < threshold
        ):
            try:
                out = provider(img, page_idx=0, dpi=200)
            except Exception as e:
                logger.warning(f"[ImageAdapter] External OCR failed: {e}")
                out = None
            if out is not None:
                logger.info(
                    f"[ImageAdapter] Delegated to external OCR (quality={quality})"
                )
                return self._text_from_ocr_result(out)
        try:
            from docmirror.core.ocr.vision.rapidocr_engine import get_ocr_engine
            engine = get_ocr_engine()
            words = engine.detect_image_words(img)
            return "\n".join(w[4] for w in words) if words else ""
        except Exception as e:
            logger.warning(f"[ImageAdapter] OCR fallback failed: {e}")
            return ""

    @staticmethod
    def _text_from_ocr_result(out) -> str:
        """Convert external OCR result (list of words or dict) to plain text."""
        if isinstance(out, list):
            return "\n".join(w[4] for w in out if len(w) > 4)
        if isinstance(out, dict):
            lines = out.get("lines", [])
            if lines:
                return "\n".join(
                    line.get("text", "") if isinstance(line, dict) else str(line)
                    for line in lines
                )
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
            return "\n".join(parts) if parts else ""
        return ""