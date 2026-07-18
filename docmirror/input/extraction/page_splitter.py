"""Detect and split rotated two-page scans before OCR.

The splitter operates on rendered page images and deliberately has no
ParseResult or Mirror dependencies.  Coordinates exposed by ``PageSlice`` are
expressed in normalized PDF points so downstream blocks can still be mapped
back to the source physical page.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import sqrt
from typing import Any, Literal

from docmirror.layout.normalization.transform import invert_matrix, rotation_matrix

PageSplitMode = Literal["auto", "off", "force"]

_TARGET_PORTRAIT_RATIO = 1.0 / sqrt(2.0)


@dataclass(frozen=True)
class SpreadAnalysis:
    rotation: int
    split_position: int
    split_ratio: float
    score: float
    gutter_density: float
    left_density: float
    right_density: float
    left_aspect: float
    right_aspect: float

    @property
    def nonblank_segments(self) -> int:
        return int(self.left_density >= 0.003) + int(self.right_density >= 0.003)


@dataclass(frozen=True)
class PageSplitDecision:
    should_split: bool = False
    rotation_candidates: tuple[int, ...] = ()
    confidence: float = 0.0
    split_ratio: float = 0.5
    expected_nonblank_segments: int = 1
    analyses: tuple[SpreadAnalysis, ...] = ()


@dataclass(frozen=True)
class DocumentSpreadPlan:
    mode: PageSplitMode = "off"
    decisions: dict[int, PageSplitDecision] = field(default_factory=dict)
    logical_starts: dict[int, int] = field(default_factory=dict)
    logical_page_count: int = 0
    confidence: float = 0.0

    def decision_for(self, source_page_number: int) -> PageSplitDecision:
        return self.decisions.get(source_page_number, PageSplitDecision())

    def logical_start_for(self, source_page_number: int) -> int:
        return self.logical_starts.get(source_page_number, source_page_number)


@dataclass(frozen=True)
class LogicalPageSlice:
    segment_index: int
    image: Any
    width: float
    height: float
    selected_rotation: int
    crop_bbox_oriented: tuple[float, float, float, float]
    source_crop_bbox: tuple[float, float, float, float]
    source_to_logical: list[list[float]]
    logical_to_source: list[list[float]]
    split_confidence: float
    is_blank: bool = False


def analyze_spread_candidates(image: Any) -> tuple[SpreadAnalysis, ...]:
    """Score two-page-spread candidates for 0, 90 and 270 degree rotations."""
    if image is None or getattr(image, "size", 0) == 0:
        return ()
    return tuple(_analyze_oriented(_rotate_image(image, rotation), rotation=rotation) for rotation in (0, 90, 270))


def decision_from_analyses(
    analyses: tuple[SpreadAnalysis, ...] | list[SpreadAnalysis],
    *,
    mode: PageSplitMode,
    consensus_boost: float = 0.0,
) -> PageSplitDecision:
    """Resolve one source page to a conservative split decision."""
    if mode == "off" or not analyses:
        return PageSplitDecision(analyses=tuple(analyses))
    ranked = sorted(analyses, key=lambda item: item.score, reverse=True)
    best = ranked[0]
    threshold = 0.78 if mode == "auto" else 0.55
    effective_score = min(1.0, best.score + max(0.0, consensus_boost))
    should_split = effective_score >= threshold and best.nonblank_segments >= 1
    rotations = tuple(
        item.rotation for item in ranked if item.rotation != 0 and item.score >= max(0.62, best.score - 0.12)
    )
    if best.rotation != 0 and best.rotation not in rotations:
        rotations = (best.rotation, *rotations)
    return PageSplitDecision(
        should_split=should_split,
        rotation_candidates=rotations,
        confidence=round(effective_score, 4),
        split_ratio=best.split_ratio,
        expected_nonblank_segments=max(1, best.nonblank_segments),
        analyses=tuple(ranked),
    )


def build_document_plan(
    analyses_by_page: dict[int, tuple[SpreadAnalysis, ...]],
    *,
    source_page_numbers: list[int],
    mode: PageSplitMode,
) -> DocumentSpreadPlan:
    """Build stable physical-to-logical numbering from thumbnail analyses."""
    if mode == "off":
        starts = {page_number: page_number for page_number in source_page_numbers}
        return DocumentSpreadPlan(
            mode=mode,
            logical_starts=starts,
            logical_page_count=len(source_page_numbers),
        )

    raw_best = [max(items, key=lambda item: item.score) for items in analyses_by_page.values() if items]
    strong_spreads = [item for item in raw_best if item.score >= 0.78 and item.rotation in {90, 270}]
    consensus_boost = 0.05 if len(strong_spreads) >= 2 else 0.0

    decisions: dict[int, PageSplitDecision] = {}
    starts: dict[int, int] = {}
    next_logical = 1
    confidences: list[float] = []
    for source_page_number in source_page_numbers:
        starts[source_page_number] = next_logical
        decision = decision_from_analyses(
            analyses_by_page.get(source_page_number, ()),
            mode=mode,
            consensus_boost=consensus_boost,
        )
        decisions[source_page_number] = decision
        page_count = decision.expected_nonblank_segments if decision.should_split else 1
        next_logical += max(1, page_count)
        if decision.should_split:
            confidences.append(decision.confidence)

    return DocumentSpreadPlan(
        mode=mode,
        decisions=decisions,
        logical_starts=starts,
        logical_page_count=max(0, next_logical - 1),
        confidence=round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
    )


def confirm_document_plan_rotation(
    plan: DocumentSpreadPlan,
    *,
    source_page_numbers: list[int],
    preferred_rotation: int | None,
) -> DocumentSpreadPlan:
    """Reconcile provisional spread decisions with the OCR orientation probe.

    Thumbnail geometry deliberately evaluates 90/270-degree candidates so a
    sideways two-page scan can be recognized before OCR.  Dense upright report
    pages can nevertheless resemble a landscape spread after that synthetic
    rotation.  Do not reserve two logical page numbers for those candidates
    unless the document-level OCR probe also confirms a sideways orientation.

    Native 0-degree landscape spreads remain eligible without an orientation
    probe.  This keeps the existing credit-report spread path while preventing
    sparse logical numbering when runtime OCR correctly keeps an upright page
    intact.
    """
    if plan.mode == "off":
        return plan

    sideways_confirmed = int(preferred_rotation or 0) % 360 in {90, 270}
    decisions: dict[int, PageSplitDecision] = {}
    starts: dict[int, int] = {}
    next_logical = 1
    confidences: list[float] = []
    for source_page_number in source_page_numbers:
        starts[source_page_number] = next_logical
        decision = plan.decision_for(source_page_number)
        best_rotation = int(decision.analyses[0].rotation) % 360 if decision.analyses else 0
        if decision.should_split and best_rotation in {90, 270} and not sideways_confirmed:
            decision = replace(
                decision,
                should_split=False,
                rotation_candidates=(),
                expected_nonblank_segments=1,
            )
        decisions[source_page_number] = decision
        page_count = decision.expected_nonblank_segments if decision.should_split else 1
        next_logical += max(1, page_count)
        if decision.should_split:
            confidences.append(decision.confidence)

    return DocumentSpreadPlan(
        mode=plan.mode,
        decisions=decisions,
        logical_starts=starts,
        logical_page_count=max(0, next_logical - 1),
        confidence=round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
    )


def split_or_passthrough(
    oriented_image: Any,
    *,
    source_width: float,
    source_height: float,
    selected_rotation: int,
    zoom: float,
    decision: PageSplitDecision,
    mode: PageSplitMode,
) -> list[LogicalPageSlice]:
    """Return one full-page slice or non-blank logical halves."""
    if oriented_image is None or getattr(oriented_image, "size", 0) == 0:
        return []

    analysis = _analyze_oriented(oriented_image, rotation=selected_rotation)
    threshold = 0.72 if mode == "auto" else 0.50
    should_split = decision.should_split and analysis.score >= threshold
    height_px, width_px = oriented_image.shape[:2]
    if not should_split:
        return [
            _make_slice(
                oriented_image,
                segment_index=0,
                crop_px=(0, 0, width_px, height_px),
                source_width=source_width,
                source_height=source_height,
                rotation=selected_rotation,
                zoom=zoom,
                confidence=analysis.score,
                is_blank=False,
            )
        ]

    split_x = analysis.split_position
    if not int(width_px * 0.30) < split_x < int(width_px * 0.70):
        split_x = int(round(width_px * decision.split_ratio))
    crops = (
        (0, 0, split_x, height_px),
        (split_x, 0, width_px, height_px),
    )
    slices: list[LogicalPageSlice] = []
    for segment_index, crop in enumerate(crops):
        x0, y0, x1, y1 = crop
        cropped = oriented_image[y0:y1, x0:x1]
        blank = _ink_density(cropped) < 0.003
        if blank:
            continue
        slices.append(
            _make_slice(
                cropped,
                segment_index=segment_index,
                crop_px=crop,
                source_width=source_width,
                source_height=source_height,
                rotation=selected_rotation,
                zoom=zoom,
                confidence=analysis.score,
                is_blank=False,
            )
        )
    if slices:
        return slices
    return [
        _make_slice(
            oriented_image,
            segment_index=0,
            crop_px=(0, 0, width_px, height_px),
            source_width=source_width,
            source_height=source_height,
            rotation=selected_rotation,
            zoom=zoom,
            confidence=analysis.score,
            is_blank=False,
        )
    ]


def _analyze_oriented(image: Any, *, rotation: int) -> SpreadAnalysis:
    import cv2
    import numpy as np

    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if len(image.shape) == 3 else image
    height, width = gray.shape[:2]
    if width < 20 or height < 20:
        return SpreadAnalysis(rotation, width // 2, 0.5, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0)

    ink = (gray < 210).astype(np.uint8)
    y0, y1 = int(height * 0.02), max(int(height * 0.98), int(height * 0.02) + 1)
    projection = ink[y0:y1].mean(axis=0)
    window = max(3, int(round(width * 0.015)))
    smoothed = np.convolve(projection, np.ones(window, dtype=float) / window, mode="same")
    search_start, search_end = int(width * 0.35), int(width * 0.65)
    split_position = search_start + int(np.argmin(smoothed[search_start:search_end]))

    left_density = float(ink[:, :split_position].mean()) if split_position > 0 else 0.0
    right_density = float(ink[:, split_position:].mean()) if split_position < width else 0.0
    gutter_density = float(smoothed[split_position])
    left_aspect = float(split_position) / float(height)
    right_aspect = float(width - split_position) / float(height)

    gutter_score = _clamp01(1.0 - gutter_density / 0.035)
    aspect_error = (abs(left_aspect - _TARGET_PORTRAIT_RATIO) + abs(right_aspect - _TARGET_PORTRAIT_RATIO)) / 2
    aspect_score = _clamp01(1.0 - aspect_error / 0.35)
    center_score = _clamp01(1.0 - abs(split_position / width - 0.5) / 0.15)
    if max(left_density, right_density) <= 0.0:
        content_score = 0.0
    elif min(left_density, right_density) < 0.003:
        content_score = 0.35
    else:
        content_score = _clamp01(min(left_density, right_density) / max(left_density, right_density))
    landscape_score = _clamp01((width / height - 1.0) / 0.25)
    score = (
        gutter_score * 0.30 + aspect_score * 0.30 + center_score * 0.15 + content_score * 0.10 + landscape_score * 0.15
    )
    return SpreadAnalysis(
        rotation=int(rotation) % 360,
        split_position=split_position,
        split_ratio=round(split_position / width, 6),
        score=round(_clamp01(score), 4),
        gutter_density=round(gutter_density, 6),
        left_density=round(left_density, 6),
        right_density=round(right_density, 6),
        left_aspect=round(left_aspect, 6),
        right_aspect=round(right_aspect, 6),
    )


def _make_slice(
    image: Any,
    *,
    segment_index: int,
    crop_px: tuple[int, int, int, int],
    source_width: float,
    source_height: float,
    rotation: int,
    zoom: float,
    confidence: float,
    is_blank: bool,
) -> LogicalPageSlice:
    x0, y0, x1, y1 = crop_px
    crop_points = (x0 / zoom, y0 / zoom, x1 / zoom, y1 / zoom)
    rotate = rotation_matrix(source_width, source_height, rotation)
    translate = [[1.0, 0.0, -crop_points[0]], [0.0, 1.0, -crop_points[1]], [0.0, 0.0, 1.0]]
    source_to_logical = _matmul3(translate, rotate)
    logical_to_source = invert_matrix(source_to_logical)
    width = (x1 - x0) / zoom
    height = (y1 - y0) / zoom
    source_crop_bbox = _transform_bbox(logical_to_source, (0.0, 0.0, width, height))
    return LogicalPageSlice(
        segment_index=segment_index,
        image=image,
        width=round(width, 4),
        height=round(height, 4),
        selected_rotation=int(rotation) % 360,
        crop_bbox_oriented=tuple(round(value, 4) for value in crop_points),
        source_crop_bbox=tuple(round(value, 4) for value in source_crop_bbox),
        source_to_logical=source_to_logical,
        logical_to_source=logical_to_source,
        split_confidence=round(float(confidence), 4),
        is_blank=is_blank,
    )


def _rotate_image(image: Any, rotation: int) -> Any:
    import cv2

    rotation = int(rotation) % 360
    if rotation == 0:
        return image
    if rotation == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if rotation == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    if rotation == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    raise ValueError(f"unsupported rotation: {rotation}")


def _ink_density(image: Any) -> float:
    import cv2

    if image is None or getattr(image, "size", 0) == 0:
        return 0.0
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if len(image.shape) == 3 else image
    return float((gray < 210).mean())


def _matmul3(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [
        [sum(float(left[row][inner]) * float(right[inner][col]) for inner in range(3)) for col in range(3)]
        for row in range(3)
    ]


def _transform_bbox(
    matrix: list[list[float]], bbox: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = bbox
    points = [_apply_matrix(matrix, x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _apply_matrix(matrix: list[list[float]], x: float, y: float) -> tuple[float, float]:
    return (
        float(matrix[0][0]) * x + float(matrix[0][1]) * y + float(matrix[0][2]),
        float(matrix[1][0]) * x + float(matrix[1][1]) * y + float(matrix[1][2]),
    )


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


__all__ = [
    "DocumentSpreadPlan",
    "LogicalPageSlice",
    "PageSplitDecision",
    "SpreadAnalysis",
    "analyze_spread_candidates",
    "build_document_plan",
    "confirm_document_plan_rotation",
    "decision_from_analyses",
    "split_or_passthrough",
]
