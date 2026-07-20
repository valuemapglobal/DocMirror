# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Lazy logical-page rendering for credit-report visual verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class LogicalPageImageResolver:
    """Render logical PDF pages on demand without running whole-page OCR again."""

    def __init__(self, parse_result: Any, *, zoom: float = 3.0) -> None:
        self._file_path = Path(str(getattr(parse_result, "file_path", "") or ""))
        self._zoom = max(1.0, float(zoom))
        self._pages: dict[int, Any] = {
            int(getattr(page, "page_number", 0) or 0): page for page in getattr(parse_result, "pages", []) or []
        }
        self._cache: dict[int, dict[str, Any] | None] = {}

    def __call__(self, logical_page: int) -> dict[str, Any] | None:
        page_number = int(logical_page or 0)
        if page_number in self._cache:
            return self._cache[page_number]
        rendered = self._render(page_number)
        self._cache[page_number] = rendered
        return rendered

    def clear(self) -> None:
        self._cache.clear()

    def _render(self, logical_page: int) -> dict[str, Any] | None:
        page = self._pages.get(logical_page)
        if page is None or not self._file_path.is_file() or self._file_path.suffix.lower() != ".pdf":
            return None
        transform = dict(getattr(page, "coordinate_transform", None) or {})
        source_page = int(
            transform.get("source_page_number") or getattr(page, "source_page_number", None) or logical_page
        )
        width = float(getattr(page, "width", 0.0) or transform.get("display_width") or 0.0)
        height = float(getattr(page, "height", 0.0) or transform.get("display_height") or 0.0)
        matrix = transform.get("matrix")
        if source_page <= 0 or width <= 0 or height <= 0 or not _is_matrix3(matrix):
            return None

        try:
            import cv2
            import fitz
            import numpy as np

            with fitz.open(self._file_path) as document:
                if source_page > len(document):
                    return None
                pix = document[source_page - 1].get_pixmap(
                    matrix=fitz.Matrix(self._zoom, self._zoom), alpha=False
                )
            source_image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n >= 3:
                source_image = source_image[:, :, :3]

            scale = np.array(
                [[self._zoom, 0.0, 0.0], [0.0, self._zoom, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64
            )
            inverse_scale = np.array(
                [[1.0 / self._zoom, 0.0, 0.0], [0.0, 1.0 / self._zoom, 0.0], [0.0, 0.0, 1.0]],
                dtype=np.float64,
            )
            logical_transform = scale @ np.asarray(matrix, dtype=np.float64) @ inverse_scale
            logical_image = cv2.warpPerspective(
                source_image,
                logical_transform,
                (max(1, int(round(width * self._zoom))), max(1, int(round(height * self._zoom)))),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(255, 255, 255),
            )
            return {
                "image": logical_image,
                "page_width": width,
                "page_height": height,
                "logical_page": logical_page,
                "source_page": source_page,
                "zoom": self._zoom,
                "coordinate_transform": transform,
            }
        except Exception:
            return None


def _is_matrix3(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 3
        and all(isinstance(row, (list, tuple)) and len(row) == 3 for row in value)
    )


__all__ = ["LogicalPageImageResolver"]
