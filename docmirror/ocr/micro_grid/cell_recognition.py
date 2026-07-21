# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Cell-level recognition helpers for scanned micro-grids."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from docmirror.ocr.micro_grid.models import BBox


@dataclass(frozen=True)
class CellRecognition:
    text: str
    confidence: float = 0.0
    source: str = "none"
    raw_text: str = ""
    audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "source": self.source,
            "raw_text": self.raw_text,
            "audit": self.audit,
        }


_CONFUSION_MAP = {
    "Ｏ": "0",
    "O": "0",
    "o": "0",
    "〇": "0",
    "。": "0",
    ".": "0",
    "·": "0",
    "Ｉ": "1",
    "l": "1",
    "|": "1",
    "Ｓ": "5",
    "S": "5",
    "×": "*",
    "✕": "*",
    "✱": "*",
    "✳": "*",
    "X": "*",
    "x": "*",
}


def normalize_allowlist_text(text: str, allowed_charset: Iterable[str], *, max_chars: int | None = None) -> str:
    """Normalize OCR text under a strict allowlist.

    This is intentionally conservative: characters outside the allowlist are
    discarded after a small OCR-confusion normalization pass.
    """
    allowed = set(allowed_charset)
    out: list[str] = []
    for ch in str(text or "").strip():
        normalized = ch if ch in allowed else _CONFUSION_MAP.get(ch, ch)
        if normalized in allowed:
            out.append(normalized)
        if max_chars is not None and len(out) >= max_chars:
            break
    return "".join(out)


def pdf_bbox_to_image_region(
    bbox: BBox,
    *,
    page_width: float,
    page_height: float,
    image_width: int,
    image_height: int,
    pad_px: int = 3,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox
    sx = image_width / max(page_width, 1.0)
    sy = image_height / max(page_height, 1.0)
    ix0 = max(0, int(round(x0 * sx)) - pad_px)
    iy0 = max(0, int(round(y0 * sy)) - pad_px)
    ix1 = min(image_width, int(round(x1 * sx)) + pad_px)
    iy1 = min(image_height, int(round(y1 * sy)) + pad_px)
    return ix0, iy0, ix1, iy1


def recognize_micro_cell_from_image(
    page_image: Any,
    bbox: BBox,
    *,
    page_width: float,
    page_height: float,
    allowed_charset: Iterable[str],
    max_chars: int | None = None,
    min_confidence: float = 0.35,
    reference_templates: dict[str, list[Any]] | None = None,
) -> CellRecognition:
    """Recognize one cell using crop-local preprocessing and consensus."""
    shape = getattr(page_image, "shape", None)
    if not shape or len(shape) < 2:
        return CellRecognition("", 0.0, "unavailable", audit={"reason": "missing_page_image"})

    image_height, image_width = int(shape[0]), int(shape[1])
    region = pdf_bbox_to_image_region(
        bbox,
        page_width=page_width,
        page_height=page_height,
        image_width=image_width,
        image_height=image_height,
        pad_px=0,
    )
    if region[2] - region[0] < 3 or region[3] - region[1] < 3:
        return CellRecognition("", 0.0, "unavailable", audit={"reason": "empty_region", "region": region})

    try:
        import cv2
        import numpy as np

        from docmirror.ocr.vision.rapidocr_engine import get_ocr_engine

        crop = page_image[region[1] : region[3], region[0] : region[2]]
        if crop is None or getattr(crop, "size", 0) == 0:
            return CellRecognition("", 0.0, "unavailable", audit={"reason": "empty_crop", "region": region})
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY) if len(crop.shape) == 3 else crop.copy()
        border = max(1, int(round(min(gray.shape[:2]) * 0.07)))
        cleaned = gray.copy()
        cleaned[:border, :] = 255
        cleaned[-border:, :] = 255
        cleaned[:, :border] = 255
        cleaned[:, -border:] = 255
        _threshold, otsu = cv2.threshold(cleaned, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        min_dim = min(cleaned.shape[:2])
        adaptive_block = min(31, min_dim if min_dim % 2 == 1 else min_dim - 1)
        adaptive = (
            cv2.adaptiveThreshold(
                cleaned,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                adaptive_block,
                7,
            )
            if adaptive_block >= 3
            else otsu
        )
        glyph_clean = _isolate_cell_glyph(otsu, np=np, cv2=cv2)
        glyph_template = _normalize_glyph_template(glyph_clean, np=np, cv2=cv2)
        variants = [
            ("gray_2x", cv2.resize(cleaned, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)),
            ("otsu_4x", cv2.resize(otsu, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_NEAREST)),
            ("adaptive_4x", cv2.resize(adaptive, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_NEAREST)),
            ("inverted_4x", cv2.resize(255 - otsu, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_NEAREST)),
            ("glyph_clean_4x", cv2.resize(glyph_clean, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_NEAREST)),
            (
                "glyph_clean_6x",
                cv2.GaussianBlur(
                    cv2.resize(glyph_clean, None, fx=6.0, fy=6.0, interpolation=cv2.INTER_CUBIC), (3, 3), 0
                ),
            ),
        ]
        engine = get_ocr_engine()
        observations: list[dict[str, Any]] = []
        for variant_name, variant in variants:
            vh, vw = variant.shape[:2]
            raw = engine.force_recognize_regions(variant, [(0, 0, vw, vh)])
            if not raw:
                observations.append({"variant": variant_name, "raw_text": "", "text": "", "confidence": 0.0})
                continue
            best = max(raw, key=lambda item: float(item[5]) if len(item) > 5 else 0.0)
            raw_text = str(best[4] if len(best) > 4 else "")
            confidence = float(best[5] if len(best) > 5 else 0.0)
            observations.append(
                {
                    "variant": variant_name,
                    "raw_text": raw_text,
                    "text": normalize_allowlist_text(raw_text, allowed_charset, max_chars=max_chars),
                    "confidence": round(confidence, 4),
                }
            )
        if max_chars == 1 and "*" in set(allowed_charset):
            star_confidence = _star_shape_confidence(otsu, np=np, cv2=cv2)
            if star_confidence >= 0.65:
                observations.append(
                    {
                        "variant": "glyph_shape",
                        "raw_text": "*",
                        "text": "*",
                        "confidence": round(star_confidence, 4),
                    }
                )
        if max_chars == 1 and "N" in set(allowed_charset) and reference_templates and reference_templates.get("N"):
            n_confidence = _n_shape_confidence(otsu, np=np, cv2=cv2)
            if n_confidence >= 0.8:
                observations.append(
                    {
                        "variant": "glyph_shape_n",
                        "raw_text": "N",
                        "text": "N",
                        "confidence": round(n_confidence, 4),
                    }
                )
        if max_chars == 1 and glyph_template is not None and reference_templates:
            template_vote = _match_reference_templates(glyph_template, reference_templates, np=np)
            if template_vote is not None:
                template_text, template_confidence = template_vote
                if template_text in set(allowed_charset):
                    observations.append(
                        {
                            "variant": "document_glyph_template",
                            "raw_text": template_text,
                            "text": template_text,
                            "confidence": round(template_confidence, 4),
                        }
                    )
    except Exception as exc:
        return CellRecognition("", 0.0, "cell_crop_ocr_error", audit={"reason": str(exc), "region": region})

    usable = [item for item in observations if item["text"] and float(item["confidence"]) >= min_confidence]
    if not usable:
        return CellRecognition(
            "",
            max((float(item["confidence"]) for item in observations), default=0.0),
            "cell_crop_consensus",
            audit={"reason": "no_reliable_vote", "region": region, "votes": observations},
        )
    counts = Counter(str(item["text"]) for item in usable)
    text, vote_count = max(
        counts.items(),
        key=lambda pair: (pair[1], max(float(item["confidence"]) for item in usable if item["text"] == pair[0])),
    )
    agreeing = [item for item in usable if item["text"] == text]
    confidence = max(float(item["confidence"]) for item in agreeing)
    # A single OCR vote is insufficient for one-character status cells. This
    # protects legitimate overdue digits from star/digit OCR confusion.
    shape_confirmed = any(
        item["variant"] in {"glyph_shape", "glyph_shape_n", "document_glyph_template"}
        and float(item["confidence"]) >= 0.8
        for item in agreeing
    )
    if max_chars == 1 and vote_count < 2 and not shape_confirmed:
        return CellRecognition(
            "",
            confidence,
            "cell_crop_consensus",
            raw_text=str(agreeing[0]["raw_text"]),
            audit={"reason": "insufficient_consensus", "region": region, "votes": observations},
        )
    best = max(agreeing, key=lambda item: float(item["confidence"]))
    return CellRecognition(
        text,
        confidence,
        "cell_crop_consensus",
        raw_text=str(best["raw_text"]),
        audit={"region": region, "votes": observations, "consensus_count": vote_count},
    )


def _star_shape_confidence(binary_white: Any, *, np: Any, cv2: Any) -> float:
    """Return conservative asterisk confidence from skeleton endpoint topology."""
    ink = (binary_white < 128).astype(np.uint8)
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(ink, connectivity=8)
    components = []
    height, width = ink.shape[:2]
    for index in range(1, count):
        x, y, w, h, area = (int(value) for value in stats[index])
        aspect = w / max(h, 1)
        if (
            area < 4
            or x <= 0
            or y <= 0
            or x + w >= width
            or y + h >= height
            or w > width * 0.65
            or h > height * 0.75
            or not 0.3 <= aspect <= 3.0
        ):
            continue
        components.append((area, labels == index, w, h))
    if not components:
        return 0.0
    _area, component, comp_width, comp_height = max(components, key=lambda item: item[0])
    aspect = comp_width / max(comp_height, 1)
    if not 0.45 <= aspect <= 2.2:
        return 0.0
    component_rows, component_cols = np.where(component)
    compact = component[
        component_rows.min() : component_rows.max() + 1,
        component_cols.min() : component_cols.max() + 1,
    ]
    if _looks_like_n(compact, np=np) or _looks_like_hash(compact, np=np):
        return 0.0
    skeleton = np.zeros_like(component, dtype=np.uint8)
    working = component.astype(np.uint8) * 255
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    for _ in range(96):
        eroded = cv2.erode(working, element)
        opened = cv2.dilate(eroded, element)
        skeleton = cv2.bitwise_or(skeleton, cv2.subtract(working, opened))
        working = eroded
        if cv2.countNonZero(working) == 0:
            break
    points = skeleton > 0
    neighbours = cv2.filter2D(points.astype(np.uint8), -1, np.ones((3, 3), dtype=np.uint8)) - points
    endpoints = int(np.count_nonzero(points & (neighbours == 1)))
    if 5 <= endpoints <= 12:
        return min(0.9, 0.62 + endpoints * 0.04)
    return 0.0


def _n_shape_confidence(binary_white: Any, *, np: Any, cv2: Any) -> float:
    isolated = _isolate_cell_glyph(binary_white, np=np, cv2=cv2)
    ys, xs = np.where(isolated < 128)
    if not len(xs):
        return 0.0
    compact = isolated[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1] < 128
    return 0.9 if _looks_like_n(compact, np=np) else 0.0


def _looks_like_n(ink: Any, *, np: Any) -> bool:
    if ink.shape[0] < 6 or ink.shape[1] < 5:
        return False
    col_density = ink.astype(np.float32).mean(axis=0)
    dense = np.where(col_density >= 0.55)[0]
    if len(dense) < 2:
        return False
    groups: list[list[int]] = []
    for value in (int(item) for item in dense):
        if not groups or value > groups[-1][-1] + 1:
            groups.append([value])
        else:
            groups[-1].append(value)
    if len(groups) < 2:
        return False
    span = max(1, groups[-1][-1] - groups[0][0] + 1)
    separation = groups[-1][0] - groups[0][-1]
    return bool(separation >= max(2, int(round(span * 0.20))))


def _looks_like_hash(ink: Any, *, np: Any) -> bool:
    if ink.shape[0] < 6 or ink.shape[1] < 6:
        return False
    rows = np.where(ink.astype(np.float32).mean(axis=1) >= 0.6)[0]
    cols = np.where(ink.astype(np.float32).mean(axis=0) >= 0.6)[0]

    def groups(values: Any) -> list[list[int]]:
        out: list[list[int]] = []
        for value in (int(item) for item in values):
            if not out or value > out[-1][-1] + 1:
                out.append([value])
            else:
                out[-1].append(value)
        return [group for group in out if len(group) >= 2]

    return bool(len(groups(rows)) >= 2 and len(groups(cols)) >= 2)


def _isolate_cell_glyph(binary_white: Any, *, np: Any, cv2: Any) -> Any:
    """Remove long table rules and retain compact glyph components."""
    ink = (binary_white < 128).astype(np.uint8)
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(ink, connectivity=8)
    height, width = ink.shape[:2]
    centre_x, centre_y = width / 2.0, height / 2.0
    candidates: list[tuple[float, int]] = []
    for index in range(1, count):
        x, y, w, h, area = (int(value) for value in stats[index])
        aspect = w / max(h, 1)
        if area < 4 or not 0.25 <= aspect <= 4.0 or w > width * 0.7 or h > height * 0.8:
            continue
        cx, cy = (float(value) for value in centroids[index])
        distance = ((cx - centre_x) / max(width, 1)) ** 2 + ((cy - centre_y) / max(height, 1)) ** 2
        candidates.append((distance - min(area, 100) / 1000.0, index))
    isolated = np.full_like(binary_white, 255)
    if not candidates:
        return isolated
    _score, selected = min(candidates)
    isolated[labels == selected] = 0
    ys, xs = np.where(isolated < 128)
    if not len(xs):
        return isolated
    pad = max(5, int(round(max(xs.max() - xs.min() + 1, ys.max() - ys.min() + 1) * 0.8)))
    glyph = isolated[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    return cv2.copyMakeBorder(glyph, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)


def extract_micro_cell_glyph_template(
    page_image: Any,
    bbox: BBox,
    *,
    page_width: float,
    page_height: float,
) -> Any | None:
    """Extract a normalized glyph bitmap for same-document template matching."""
    shape = getattr(page_image, "shape", None)
    if not shape or len(shape) < 2:
        return None
    try:
        import cv2
        import numpy as np

        region = pdf_bbox_to_image_region(
            bbox,
            page_width=page_width,
            page_height=page_height,
            image_width=int(shape[1]),
            image_height=int(shape[0]),
            pad_px=0,
        )
        crop = page_image[region[1] : region[3], region[0] : region[2]]
        if crop is None or getattr(crop, "size", 0) == 0:
            return None
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY) if len(crop.shape) == 3 else crop.copy()
        border = max(1, int(round(min(gray.shape[:2]) * 0.07)))
        gray[:border, :] = 255
        gray[-border:, :] = 255
        gray[:, :border] = 255
        gray[:, -border:] = 255
        _threshold, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        isolated = _isolate_cell_glyph(binary, np=np, cv2=cv2)
        return _normalize_glyph_template(isolated, np=np, cv2=cv2)
    except Exception:
        return None


def _normalize_glyph_template(glyph_white: Any, *, np: Any, cv2: Any) -> Any | None:
    ys, xs = np.where(glyph_white < 128)
    if not len(xs):
        return None
    glyph = glyph_white[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    ink_full = (glyph < 128).astype(np.float32)
    dense_cols = np.where(ink_full.mean(axis=0) >= max(0.12, 2.0 / max(ink_full.shape[0], 1)))[0]
    dense_rows = np.where(ink_full.mean(axis=1) >= max(0.12, 2.0 / max(ink_full.shape[1], 1)))[0]
    if len(dense_cols) and len(dense_rows):
        x0 = max(0, int(dense_cols.min()) - 1)
        x1 = min(glyph.shape[1], int(dense_cols.max()) + 2)
        y0 = max(0, int(dense_rows.min()) - 1)
        y1 = min(glyph.shape[0], int(dense_rows.max()) + 2)
        glyph = glyph[y0:y1, x0:x1]
    height, width = glyph.shape[:2]
    scale = min(22.0 / max(width, 1), 22.0 / max(height, 1))
    resized = cv2.resize(
        glyph,
        (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
        interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_NEAREST,
    )
    canvas = np.zeros((32, 32), dtype=np.float32)
    ink = (resized < 128).astype(np.float32)
    y0 = (32 - ink.shape[0]) // 2
    x0 = (32 - ink.shape[1]) // 2
    canvas[y0 : y0 + ink.shape[0], x0 : x0 + ink.shape[1]] = ink
    return canvas


def _match_reference_templates(target: Any, references: dict[str, list[Any]], *, np: Any) -> tuple[str, float] | None:
    target_norm = float(np.linalg.norm(target))
    if target_norm <= 0:
        return None
    scores: list[tuple[float, str]] = []
    for text, templates in references.items():
        for reference in templates[:12]:
            ref_norm = float(np.linalg.norm(reference))
            if ref_norm <= 0:
                continue
            best = 0.0
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    shifted = np.roll(np.roll(reference, dy, axis=0), dx, axis=1)
                    best = max(best, float((target * shifted).sum()) / (target_norm * ref_norm))
            scores.append((best, str(text)))
    if not scores:
        return None
    scores.sort(reverse=True)
    score, text = scores[0]
    runner_up = next((value for value, label in scores[1:] if label != text), 0.0)
    if score < 0.58 or score - runner_up < 0.08:
        return None
    return text, min(0.96, 0.55 + score * 0.45)
