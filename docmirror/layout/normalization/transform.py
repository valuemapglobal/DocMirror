"""Coordinate transform helpers for UDTR normalization."""

from __future__ import annotations

from math import isfinite
from typing import Any

from docmirror.layout.normalization.models import NormalizationCandidate, NormalizationTrace


def rotation_matrix(page_w: float, page_h: float, rotation: int) -> list[list[float]]:
    """Return a 3x3 affine matrix for normalized page rotation."""
    rotation = int(rotation or 0) % 360
    if rotation == 90:
        return [[0.0, -1.0, float(page_h)], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
    if rotation == 180:
        return [[-1.0, 0.0, float(page_w)], [0.0, -1.0, float(page_h)], [0.0, 0.0, 1.0]]
    if rotation == 270:
        return [[0.0, 1.0, 0.0], [-1.0, 0.0, float(page_w)], [0.0, 0.0, 1.0]]
    return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def invert_matrix(matrix: list[list[float]]) -> list[list[float]]:
    """Invert a 2D affine 3x3 matrix."""
    if len(matrix) != 3 or any(len(row) != 3 for row in matrix):
        return []
    a, c, e = float(matrix[0][0]), float(matrix[0][1]), float(matrix[0][2])
    b, d, f = float(matrix[1][0]), float(matrix[1][1]), float(matrix[1][2])
    det = a * d - b * c
    if abs(det) < 1e-12:
        return []
    inv_a = d / det
    inv_b = -b / det
    inv_c = -c / det
    inv_d = a / det
    inv_e = (c * f - d * e) / det
    inv_f = (b * e - a * f) / det
    return [[inv_a, inv_c, inv_e], [inv_b, inv_d, inv_f], [0.0, 0.0, 1.0]]


def is_invertible_matrix(matrix: list[list[float]]) -> bool:
    inv = invert_matrix(matrix)
    return bool(inv) and all(isfinite(value) for row in inv for value in row)


def build_identity_trace(
    *,
    page_id: str,
    width: float | None,
    height: float | None,
    source_rotation: int = 0,
) -> NormalizationTrace:
    return build_normalization_trace(
        page_id=page_id,
        source_width=float(width or 0.0),
        source_height=float(height or 0.0),
        source_rotation=source_rotation,
        selected_content_rotation=source_rotation,
        selected_reason="identity" if int(source_rotation or 0) % 360 == 0 else "source_rotation",
        confidence=1.0,
    )


def build_normalization_trace(
    *,
    page_id: str,
    source_width: float,
    source_height: float,
    source_rotation: int = 0,
    selected_content_rotation: int = 0,
    deskew_angle: float = 0.0,
    scale: float = 1.0,
    candidates: list[NormalizationCandidate] | None = None,
    selected_reason: str = "identity",
    confidence: float = 1.0,
    metadata: dict[str, Any] | None = None,
) -> NormalizationTrace:
    rotation = int(selected_content_rotation or 0) % 360
    source_width = float(source_width or 0.0)
    source_height = float(source_height or 0.0)
    display_width = source_height if rotation in {90, 270} else source_width
    display_height = source_width if rotation in {90, 270} else source_height
    if metadata:
        display_width = float(metadata.get("normalized_page_width") or display_width)
        display_height = float(metadata.get("normalized_page_height") or display_height)
    matrix = rotation_matrix(source_width, source_height, rotation)
    inverse = invert_matrix(matrix)
    return NormalizationTrace(
        page_id=page_id,
        source_width=source_width,
        source_height=source_height,
        display_width=display_width,
        display_height=display_height,
        source_rotation=int(source_rotation or 0) % 360,
        selected_content_rotation=rotation,
        deskew_angle=float(deskew_angle or 0.0),
        scale=float(scale or 1.0),
        matrix=matrix,
        inverse_matrix=inverse,
        candidates=candidates or [
            NormalizationCandidate(rotation=rotation, deskew_angle=deskew_angle, score=float(confidence or 0.0))
        ],
        selected_reason=selected_reason,
        confidence=float(confidence if confidence is not None else 1.0),
    )
