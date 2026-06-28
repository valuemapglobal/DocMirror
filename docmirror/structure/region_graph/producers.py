"""RegionGraph candidate producers and conservative candidate fusion."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol

from docmirror.structure.region_graph.models import RegionCandidate


class RegionCandidateProducer(Protocol):
    """Produces detector-first region candidates for one page."""

    producer_id: str

    def produce(self, *, page_id: str, regions: Sequence[Any]) -> list[RegionCandidate]:
        """Return candidates without mutating source regions."""


@dataclass(frozen=True)
class RegionCandidateBatch:
    candidates: list[RegionCandidate]
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class TopologyRegionCandidateProducer:
    """Compatibility producer that exposes existing topology regions as candidates."""

    producer_id: str = "topology_region_candidate_producer"

    def produce(self, *, page_id: str, regions: Sequence[Any]) -> list[RegionCandidate]:
        return [
            candidate_from_region(index=index, region=region, page_id=page_id, producer_id=self.producer_id)
            for index, region in enumerate(regions, start=1)
        ]


@dataclass(frozen=True)
class KindFilteredRegionCandidateProducer:
    """Producer boundary for one detector-owned family of topology regions."""

    producer_id: str
    accepted_kinds: frozenset[str]

    def produce(self, *, page_id: str, regions: Sequence[Any]) -> list[RegionCandidate]:
        return [
            candidate_from_region(index=index, region=region, page_id=page_id, producer_id=self.producer_id)
            for index, region in enumerate(regions, start=1)
            if str(getattr(region, "kind", "") or "") in self.accepted_kinds
        ]


def default_region_candidate_producers() -> list[RegionCandidateProducer]:
    return [
        KindFilteredRegionCandidateProducer("text_region_candidate_producer", frozenset({"text", "heading", "header", "footer", "footnote"})),
        KindFilteredRegionCandidateProducer("table_region_candidate_producer", frozenset({"table_like"})),
        KindFilteredRegionCandidateProducer("visual_region_candidate_producer", frozenset({"figure", "image", "seal", "signature"})),
        KindFilteredRegionCandidateProducer("residual_region_candidate_producer", frozenset({"residual", "unknown"})),
    ]


def produce_region_candidates(
    *,
    page_id: str,
    regions: Sequence[Any],
    producers: Sequence[RegionCandidateProducer] | None = None,
) -> RegionCandidateBatch:
    """Run candidate producers and return a single detector-first candidate list."""

    active_producers = list(producers or default_region_candidate_producers())
    candidates: list[RegionCandidate] = []
    producer_counts: dict[str, int] = {}
    for producer in active_producers:
        produced = producer.produce(page_id=page_id, regions=regions)
        candidates.extend(produced)
        producer_counts[producer.producer_id] = len(produced)
    return RegionCandidateBatch(
        candidates=candidates,
        diagnostics={
            "candidate_producer_count": len(active_producers),
            "candidate_producer_ids": [producer.producer_id for producer in active_producers],
            "candidate_producer_counts": producer_counts,
        },
    )


def candidate_from_region(
    *,
    index: int,
    region: Any,
    page_id: str | None = None,
    producer_id: str = "topology_region_candidate_producer",
) -> RegionCandidate:
    diagnostics = getattr(region, "diagnostics", {}) or {}
    grouping = str(diagnostics.get("grouping") or diagnostics.get("source") or "topology_region")
    region_id = str(getattr(region, "id", "") or "")
    return RegionCandidate(
        candidate_id=f"cand:{region_id or index}",
        page_id=str(page_id or getattr(region, "page_id", "") or ""),
        kind=str(getattr(region, "kind", "") or "unknown"),
        role_hint=str(getattr(region, "role", "") or ""),
        bbox=list(getattr(region, "bbox", None) or []) or None,
        evidence_ids=[str(eid) for eid in getattr(region, "evidence_ids", []) or []],
        detector=grouping,
        confidence=float(getattr(region, "confidence", 1.0) or 0.0),
        features={
            **{
                key: value
                for key, value in diagnostics.items()
                if key
                in {
                    "atom_count",
                    "row_count",
                    "column_count",
                    "grid_confidence",
                    "extraction_confidence",
                    "ocr_orientation_score",
                }
            },
            "producer_id": producer_id,
        },
        selected_region_id=region_id,
        source_region_ids=[region_id] if region_id else [],
    )


def merge_equivalent_candidates(
    candidates: Iterable[RegionCandidate],
    *,
    iou_threshold: float = 0.9,
) -> tuple[list[RegionCandidate], list[dict[str, Any]], dict[str, Any]]:
    """Merge same-kind, near-identical candidates in the candidate graph.

    Topology regions are not removed here. The merged candidate retains source
    region references so diagnostics and gates can still explain every region.
    """

    candidate_list = list(candidates)
    kept: list[RegionCandidate] = []
    rejected: list[dict[str, Any]] = []
    merge_count = 0
    for candidate in candidate_list:
        merge_index = _find_merge_target(candidate, kept, iou_threshold=iou_threshold)
        if merge_index is None:
            kept.append(candidate)
            continue

        existing = kept[merge_index]
        winner, loser = _winner_loser(existing, candidate)
        merged = _merge_pair(winner, loser, iou_threshold=iou_threshold)
        kept[merge_index] = merged
        merge_count += 1
        rejected.append(
            {
                "candidate_id": loser.candidate_id,
                "candidate_region_id": loser.selected_region_id,
                "source_region_ids": list(loser.source_region_ids or ([loser.selected_region_id] if loser.selected_region_id else [])),
                "reason": "merged_duplicate_candidate",
                "winner_candidate_id": winner.candidate_id,
                "winner_region_id": winner.selected_region_id,
                "iou": round(_bbox_iou(existing.bbox, candidate.bbox), 4),
            }
        )

    return kept, rejected, {
        "merged_candidate_count": merge_count,
        "candidate_count_before_merge": len(candidate_list),
        "candidate_count_after_merge": len(kept),
        "candidate_merge_iou_threshold": iou_threshold,
    }


def _find_merge_target(
    candidate: RegionCandidate,
    kept: Sequence[RegionCandidate],
    *,
    iou_threshold: float,
) -> int | None:
    if _is_overlay_candidate(candidate) or not candidate.bbox:
        return None
    for index, existing in enumerate(kept):
        if existing.page_id != candidate.page_id or existing.kind != candidate.kind:
            continue
        if _is_overlay_candidate(existing) or not existing.bbox:
            continue
        if _bbox_iou(existing.bbox, candidate.bbox) >= iou_threshold:
            return index
    return None


def _merge_pair(
    winner: RegionCandidate,
    loser: RegionCandidate,
    *,
    iou_threshold: float,
) -> RegionCandidate:
    source_region_ids = _unique(
        [
            *winner.source_region_ids,
            *loser.source_region_ids,
            *([winner.selected_region_id] if winner.selected_region_id else []),
            *([loser.selected_region_id] if loser.selected_region_id else []),
        ]
    )
    merged_ids = _unique([
        *winner.merged_candidate_ids,
        *loser.merged_candidate_ids,
        loser.candidate_id,
    ])
    detectors = _unique([
        *(str(value) for value in winner.features.get("merged_detector_ids", []) if value),
        *(str(value) for value in loser.features.get("merged_detector_ids", []) if value),
        winner.detector,
        loser.detector,
    ])
    producer_ids = _unique([
        *(str(value) for value in winner.features.get("merged_producer_ids", []) if value),
        *(str(value) for value in loser.features.get("merged_producer_ids", []) if value),
        str(winner.features.get("producer_id") or ""),
        str(loser.features.get("producer_id") or ""),
    ])
    return replace(
        winner,
        bbox=_union_bbox([winner.bbox, loser.bbox]),
        evidence_ids=_unique([*winner.evidence_ids, *loser.evidence_ids]),
        confidence=max(winner.confidence, loser.confidence),
        features={
            **winner.features,
            "merged_detector_ids": detectors,
            "merged_producer_ids": producer_ids,
            "merge_iou_threshold": iou_threshold,
        },
        source_region_ids=source_region_ids,
        merged_candidate_ids=merged_ids,
        merge_reason="same_kind_high_iou",
    )


def _winner_loser(left: RegionCandidate, right: RegionCandidate) -> tuple[RegionCandidate, RegionCandidate]:
    left_score = (left.confidence, len(left.evidence_ids), left.candidate_id)
    right_score = (right.confidence, len(right.evidence_ids), right.candidate_id)
    if left_score >= right_score:
        return left, right
    return right, left


def _is_overlay_candidate(candidate: RegionCandidate) -> bool:
    return candidate.kind in {"seal", "signature"} or candidate.role_hint in {"seal", "signature"}


def _bbox_iou(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right:
        return 0.0
    intersection = _bbox_intersection_area(left, right)
    if intersection <= 0:
        return 0.0
    left_area = _bbox_area(left)
    right_area = _bbox_area(right)
    return intersection / max(left_area + right_area - intersection, 1.0)


def _bbox_area(bbox: list[float]) -> float:
    x0, y0, x1, y1 = [float(v) for v in bbox[:4]]
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _bbox_intersection_area(left: list[float], right: list[float]) -> float:
    lx0, ly0, lx1, ly1 = [float(v) for v in left[:4]]
    rx0, ry0, rx1, ry1 = [float(v) for v in right[:4]]
    ix0, iy0 = max(lx0, rx0), max(ly0, ry0)
    ix1, iy1 = min(lx1, rx1), min(ly1, ry1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return (ix1 - ix0) * (iy1 - iy0)


def _union_bbox(bboxes: Iterable[list[float] | None]) -> list[float] | None:
    valid = [bbox for bbox in bboxes if bbox and len(bbox) == 4]
    if not valid:
        return None
    return [
        min(float(bbox[0]) for bbox in valid),
        min(float(bbox[1]) for bbox in valid),
        max(float(bbox[2]) for bbox in valid),
        max(float(bbox[3]) for bbox in valid),
    ]


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "")
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out
