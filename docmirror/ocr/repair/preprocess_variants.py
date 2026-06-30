# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Preprocessing variants for local OCR repair crops."""

from __future__ import annotations

from typing import Any


def build_preprocess_variants(crop: Any) -> list[tuple[str, Any]]:
    """Return conservative image variants for OCR.

    The function is optional-dependency tolerant.  If OpenCV is unavailable or a
    transform fails, the original crop remains usable.
    """
    variants: list[tuple[str, Any]] = [("original", crop)]
    try:
        import cv2
        import numpy as np
    except Exception:
        return variants

    try:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
        variants.append(("gray", cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)))

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        variants.append(("clahe", cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)))

        sharp_kernel = np.array([[0, -0.5, 0], [-0.5, 3, -0.5], [0, -0.5, 0]], dtype=np.float32)
        sharpened = cv2.filter2D(enhanced, -1, sharp_kernel)
        variants.append(("clahe_sharp", cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)))

        binary = cv2.adaptiveThreshold(
            enhanced,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            15,
            9,
        )
        variants.append(("adaptive_binary", cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)))
    except Exception:
        return variants
    return variants


__all__ = ["build_preprocess_variants"]
