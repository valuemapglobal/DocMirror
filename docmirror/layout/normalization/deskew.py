"""Deskew estimators for the UDTR normalization plane."""

from __future__ import annotations

from math import atan2, degrees, isfinite
from statistics import median
from typing import Any


def estimate_deskew_angle(page_or_image: Any) -> float:
    """Return a conservative page deskew angle in degrees.

    The estimator intentionally prefers high-precision, low-recall signals:
    vector line segments first, OCR/text baselines second, and image Hough lines
    last when OpenCV/numpy are available. It returns ``0.0`` whenever evidence is
    weak, because an incorrect deskew is more damaging than a missed one.
    """

    angles = [
        *_angles_from_vector_lines(page_or_image),
        *_angles_from_text_bboxes(page_or_image),
        *_angles_from_image(page_or_image),
    ]
    near_horizontal = [angle for angle in angles if -15.0 <= angle <= 15.0 and abs(angle) >= 0.05]
    if len(near_horizontal) < 2:
        return 0.0
    estimate = float(median(near_horizontal))
    if not isfinite(estimate) or abs(estimate) > 5.0:
        return 0.0
    return round(estimate, 4)


def _angles_from_vector_lines(page_or_image: Any) -> list[float]:
    lines = _iter_items(page_or_image, ("vector_lines", "lines", "edges"))
    out: list[float] = []
    for line in lines:
        x0, y0, x1, y1 = _line_points(line)
        if x0 is None:
            continue
        dx = float(x1) - float(x0)
        dy = float(y1) - float(y0)
        if abs(dx) < 24 or abs(dx) < abs(dy) * 3:
            continue
        out.append(_normalize_angle(degrees(atan2(dy, dx))))
    return out


def _angles_from_text_bboxes(page_or_image: Any) -> list[float]:
    tokens = _iter_items(page_or_image, ("tokens", "ocr_tokens", "text_atoms", "texts"))
    boxes: list[list[float]] = []
    for token in tokens:
        bbox = _bbox(token)
        if bbox and len(bbox) >= 4:
            boxes.append([float(v) for v in bbox[:4]])
    if len(boxes) < 4:
        return []
    boxes.sort(key=lambda box: ((box[1] + box[3]) / 2.0, box[0]))
    heights = [max(1.0, box[3] - box[1]) for box in boxes]
    line_tolerance = max(3.0, median(heights) * 0.8)
    lines: list[list[list[float]]] = []
    for box in boxes:
        cy = (box[1] + box[3]) / 2.0
        if not lines:
            lines.append([box])
            continue
        previous_cy = median([(item[1] + item[3]) / 2.0 for item in lines[-1]])
        if abs(cy - previous_cy) <= line_tolerance:
            lines[-1].append(box)
        else:
            lines.append([box])

    out: list[float] = []
    for line in lines:
        if len(line) < 3:
            continue
        first, last = min(line, key=lambda box: box[0]), max(line, key=lambda box: box[2])
        dx = ((last[0] + last[2]) / 2.0) - ((first[0] + first[2]) / 2.0)
        dy = ((last[1] + last[3]) / 2.0) - ((first[1] + first[3]) / 2.0)
        if abs(dx) >= 40:
            out.append(_normalize_angle(degrees(atan2(dy, dx))))
    return out


def _angles_from_image(page_or_image: Any) -> list[float]:
    image = _image_array(page_or_image)
    if image is None:
        return []
    try:
        import cv2
        import numpy as np
    except Exception:
        return []
    try:
        arr = np.asarray(image)
        if arr.size == 0:
            return []
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY) if arr.ndim == 3 else arr
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        min_len = max(32, int(min(gray.shape[:2]) * 0.15))
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=min_len, maxLineGap=12)
        if lines is None:
            return []
        out: list[float] = []
        for item in lines[:200]:
            x0, y0, x1, y1 = [float(v) for v in item[0]]
            dx = x1 - x0
            dy = y1 - y0
            if abs(dx) >= min_len and abs(dx) >= abs(dy) * 3:
                out.append(_normalize_angle(degrees(atan2(dy, dx))))
        return out
    except Exception:
        return []


def _iter_items(source: Any, names: tuple[str, ...]) -> list[Any]:
    for name in names:
        value = _get(source, name)
        if isinstance(value, list | tuple):
            return list(value)
    if isinstance(source, list | tuple):
        return list(source)
    return []


def _line_points(line: Any) -> tuple[float | None, float | None, float | None, float | None]:
    if isinstance(line, dict):
        if {"x0", "y0", "x1", "y1"} <= set(line):
            return float(line["x0"]), float(line["y0"]), float(line["x1"]), float(line["y1"])
        if isinstance(line.get("bbox"), list | tuple) and len(line["bbox"]) >= 4:
            x0, y0, x1, y1 = line["bbox"][:4]
            return float(x0), float(y0), float(x1), float(y1)
    if isinstance(line, list | tuple) and len(line) >= 4:
        x0, y0, x1, y1 = line[:4]
        return float(x0), float(y0), float(x1), float(y1)
    return None, None, None, None


def _bbox(item: Any) -> list[float] | None:
    value = _get(item, "bbox")
    if isinstance(value, list | tuple) and len(value) >= 4:
        return [float(v) for v in value[:4]]
    if isinstance(item, list | tuple) and len(item) >= 4:
        return [float(v) for v in item[:4]]
    return None


def _image_array(source: Any) -> Any:
    for name in ("image", "array", "pixels"):
        value = _get(source, name)
        if value is not None:
            return value
    return source if _looks_like_image(source) else None


def _get(source: Any, name: str) -> Any:
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def _looks_like_image(source: Any) -> bool:
    shape = getattr(source, "shape", None)
    return isinstance(shape, tuple) and len(shape) >= 2


def _normalize_angle(angle: float) -> float:
    while angle <= -90.0:
        angle += 180.0
    while angle > 90.0:
        angle -= 180.0
    return angle
