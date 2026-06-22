# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Image Probe — lightweight pre-extraction check for image validity and quality.

Purpose: Decode image headers/metadata to determine if the file is a valid visual
medium before dispatch to OCR pipeline. Returns structured result with pixel
dimensions, decode status, and quality score so the dispatcher can reject
invalid images early.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ImageProbeResult:
    """Image probe outcome."""

    status: str = "unknown"  # ok | invalid | low_quality | unreadable
    width: int = 0
    height: int = 0
    channels: int = 0
    format_name: str = ""
    quality_score: float = 0.0  # 0.0–1.0, 1.0 = perfect
    error_code: str = ""
    error_message: str = ""


def probe_image(path: Path, quality_threshold: float = 0.3) -> ImageProbeResult:
    """Open image with OpenCV and classify its validity and quality."""
    import cv2

    result = ImageProbeResult()

    if not path.is_file():
        result.status = "unreadable"
        result.error_code = "FILE_NOT_FOUND"
        result.error_message = f"File not found: {path}"
        return result

    try:
        img = cv2.imread(str(path))
    except Exception as e:
        result.status = "invalid"
        result.error_code = "INVALID_IMAGE"
        result.error_message = f"OpenCV decode exception: {e}"
        logger.warning("[ImageProbe] Decode failed: %s — %s", path.name, e)
        return result

    if img is None:
        # Try with PIL as fallback
        try:
            from PIL import Image
            pil_img = Image.open(path)
            pil_img.verify()
            result.format_name = pil_img.format or ""
            result.width, result.height = pil_img.size
            # If PIL verifies but OpenCV couldn't read, use PIL's data
            pil_img = Image.open(path)
            img_rgb = pil_img.convert("RGB")
            import numpy as np
            img = np.array(img_rgb)
            result.channels = 3
        except Exception as e:
            result.status = "invalid"
            result.error_code = "INVALID_IMAGE"
            result.error_message = f"Image decode failed: {e}"
            logger.warning("[ImageProbe] All decoders failed: %s — %s", path.name, e)
            return result
    else:
        result.channels = img.shape[2] if len(img.shape) > 2 else 1
        result.width = img.shape[1]
        result.height = img.shape[0]

    # Quality assessment
    total_pixels = result.width * result.height
    if total_pixels == 0:
        result.status = "invalid"
        result.error_code = "INVALID_IMAGE"
        result.error_message = "Image has zero pixels"
        return result

    # Score based on resolution: tiny images get low quality
    if total_pixels < 10000:  # < 100x100
        result.quality_score = 0.1
    elif total_pixels < 100000:  # < ~316x316
        result.quality_score = 0.4
    elif total_pixels < 1000000:  # < ~1000x1000
        result.quality_score = 0.7
    else:
        result.quality_score = 0.9

    if result.quality_score < quality_threshold:
        result.status = "low_quality"
        result.error_code = "LOW_QUALITY_IMAGE"
        result.error_message = f"Image quality too low ({result.quality_score:.2f})"
    else:
        result.status = "ok"

    logger.info(
        "[ImageProbe] %s → status=%s | %dx%d | quality=%.2f",
        path.name, result.status, result.width, result.height, result.quality_score
    )
    return result
