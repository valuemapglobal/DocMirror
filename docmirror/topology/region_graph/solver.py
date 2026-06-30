"""Conservative RegionGraph solver."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Any

from docmirror.topology.region_graph.models import OwnershipLedger, RegionCandidate, RegionGraph
from docmirror.topology.region_graph.producers import merge_equivalent_candidates, produce_region_candidates


def solve_region_graph(
    *,
    page_id: str,
    regions: list[Any],
    all_evidence_ids: list[str],
    candidates: list[RegionCandidate] | None = None,
    candidate_diagnostics: dict[str, Any] | None = None,
    evidence_by_id: dict[str, Any] | None = None,
) -> RegionGraph:
    producer_diagnostics: dict[str, Any] = dict(candidate_diagnostics or {})
    if candidates is None:
        candidate_batch = produce_region_candidates(page_id=page_id, regions=regions)
        candidates = candidate_batch.candidates
        producer_diagnostics = candidate_batch.diagnostics
    candidates, merge_rejections, merge_stats = merge_equivalent_candidates(candidates)
    candidates, graph_rejections, graph_stats = _enrich_candidate_relationships(candidates)
    graph_stats["duplicate_candidate_count"] = int(graph_stats.get("duplicate_candidate_count", 0) or 0) + int(
        merge_stats.get("merged_candidate_count", 0) or 0
    )
    owned: dict[str, str] = {}
    nested: dict[str, list[str]] = {}
    overlay: dict[str, str] = {}
    rejected: list[dict[str, Any]] = [*merge_rejections, *graph_rejections]

    for region in regions:
        region_id = str(getattr(region, "id", "") or "")
        evidence_ids = [str(eid) for eid in getattr(region, "evidence_ids", []) or []]
        is_overlay_region = str(getattr(region, "kind", "")) in {"seal", "signature"} or str(
            getattr(region, "role", "")
        ) in {
            "seal",
            "signature",
        }
        for evidence_id in evidence_ids:
            if evidence_id in owned and owned[evidence_id] != region_id:
                nested.setdefault(evidence_id, [owned[evidence_id]])
                if region_id not in nested[evidence_id]:
                    nested[evidence_id].append(region_id)
                rejected.append(
                    {
                        "candidate_region_id": region_id,
                        "evidence_id": evidence_id,
                        "reason": "evidence_already_owned",
                        "owner_region_id": owned[evidence_id],
                    }
                )
                continue
            owned[evidence_id] = region_id
        if is_overlay_region:
            target = _nearest_underlay(region, regions)
            if target:
                overlay[region_id] = target

    all_ids = {str(eid) for eid in all_evidence_ids}
    residual = sorted(all_ids - set(owned))
    candidate_claims_by_evidence = _candidate_claims_by_evidence(candidates)
    residual_explanations = [
        _residual_explanation(evidence_id, candidate_claims_by_evidence, evidence_by_id or {})
        for evidence_id in residual
    ]
    return RegionGraph(
        page_id=page_id,
        candidates=candidates,
        ownership=OwnershipLedger(
            owned=owned,
            nested=nested,
            overlay=overlay,
            residual=residual,
            rejected_candidates=rejected,
        ),
        diagnostics={
            "selected_candidate_count": len(candidates),
            "residual_count": len(residual),
            "residual_explanations": residual_explanations,
            "overlay_count": len(overlay),
            "nested_evidence_count": len(nested),
            **producer_diagnostics,
            **merge_stats,
            **graph_stats,
        },
    )


def _candidate_claims_by_evidence(candidates: list[RegionCandidate]) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    for candidate in candidates:
        for evidence_id in candidate.evidence_ids or []:
            key = str(evidence_id)
            out.setdefault(key, [])
            claim = {
                "candidate_id": candidate.candidate_id,
                "kind": candidate.kind,
                "detector": candidate.detector,
                "producer_id": str((candidate.features or {}).get("producer_id") or ""),
                "selected_region_id": candidate.selected_region_id,
            }
            if claim not in out[key]:
                out[key].append(claim)
    return {
        key: sorted(values, key=lambda item: (item["candidate_id"], item["detector"], item["producer_id"]))
        for key, values in out.items()
    }


def _residual_explanation(
    evidence_id: str,
    candidate_claims_by_evidence: dict[str, list[dict[str, str]]],
    evidence_by_id: dict[str, Any],
) -> dict[str, Any]:
    candidate_claims = candidate_claims_by_evidence.get(evidence_id, [])
    if candidate_claims:
        candidate_ids = sorted({claim["candidate_id"] for claim in candidate_claims if claim.get("candidate_id")})
        detectors = sorted({claim["detector"] for claim in candidate_claims if claim.get("detector")})
        producer_ids = sorted({claim["producer_id"] for claim in candidate_claims if claim.get("producer_id")})
        kinds = sorted({claim["kind"] for claim in candidate_claims if claim.get("kind")})
        return {
            "evidence_id": evidence_id,
            "reason": "candidate_not_selected",
            "candidate_ids": candidate_ids,
            "candidate_count": len(candidate_ids),
            "candidate_kinds": kinds,
            "candidate_detectors": detectors,
            "candidate_producer_ids": producer_ids,
            "detector_reason": "candidate_claim_exists_but_no_selected_region_ownership",
        }
    detector_reason, atom_payload = _no_candidate_detector_reason(evidence_id, evidence_by_id)
    explanation = {
        "evidence_id": evidence_id,
        "reason": "no_detector_candidate_claim",
        "candidate_count": 0,
        "detector_reason": detector_reason,
    }
    if atom_payload:
        explanation["atom"] = atom_payload
    return explanation


def _no_candidate_detector_reason(evidence_id: str, evidence_by_id: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    atom = evidence_by_id.get(evidence_id)
    if atom is None:
        return "evidence_atom_missing_from_index", {}
    kind = str(getattr(atom, "kind", "") or "")
    source_kind = str(getattr(atom, "source_kind", "") or "")
    bbox = getattr(atom, "bbox", None)
    metadata = getattr(atom, "metadata", {}) or {}
    atom_payload = {
        "kind": kind,
        "source_kind": source_kind,
        "has_bbox": bool(bbox),
    }
    if isinstance(metadata, dict):
        atom_payload["block_type"] = str(metadata.get("block_type") or "")
        atom_payload["role"] = str(metadata.get("role") or metadata.get("artifact_type") or "")

    if kind == "text_token":
        block_type = str(metadata.get("block_type") or "") if isinstance(metadata, dict) else ""
        if not bbox:
            return "text_detector_skipped_atom_without_bbox", atom_payload
        if block_type == "table":
            return "table_detector_skipped_or_rejected_text_atom", atom_payload
        if block_type == "key_value":
            return "key_value_detector_skipped_or_rejected_text_atom", atom_payload
        if "ocr" in source_kind.lower():
            return "ocr_text_detector_skipped_or_rejected_atom", atom_payload
        return "text_detector_skipped_or_rejected_atom", atom_payload
    if kind in {"rectangle", "line"}:
        return "vector_detector_skipped_or_rejected_atom", atom_payload
    if kind in {"embedded_image", "rendered_image"}:
        role = str(metadata.get("role") or "") if isinstance(metadata, dict) else ""
        if role in {"page_background", "rendered_page"}:
            return "page_projection_detector_skipped_or_suppressed_background_image", atom_payload
        return "image_detector_skipped_or_rejected_atom", atom_payload
    if kind == "visual_artifact":
        artifact_type = str(metadata.get("artifact_type") or "") if isinstance(metadata, dict) else ""
        if artifact_type in {"seal", "red_seal", "stamp"}:
            return "seal_detector_output_not_claimed_by_region", atom_payload
        if artifact_type == "signature":
            return "signature_detector_output_not_claimed_by_region", atom_payload
        return "visual_artifact_detector_output_not_claimed_by_region", atom_payload
    return "unsupported_atom_kind_for_region_detectors", atom_payload


def _nearest_underlay(region: Any, regions: list[Any]) -> str:
    bbox = getattr(region, "bbox", None)
    if not bbox:
        return ""
    best: tuple[float, str] | None = None
    for other in regions:
        other_id = str(getattr(other, "id", "") or "")
        if other is region or not other_id:
            continue
        other_kind = str(getattr(other, "kind", "") or "")
        if other_kind in {"seal", "signature", "residual"}:
            continue
        other_bbox = getattr(other, "bbox", None)
        if not other_bbox:
            continue
        overlap = _bbox_intersection_area(bbox, other_bbox)
        if overlap <= 0:
            continue
        if best is None or overlap > best[0]:
            best = (overlap, other_id)
    return best[1] if best else ""


def _enrich_candidate_relationships(
    candidates: list[RegionCandidate],
) -> tuple[list[RegionCandidate], list[dict[str, Any]], dict[str, int]]:
    competing: dict[str, set[str]] = defaultdict(set)
    parents: dict[str, set[str]] = defaultdict(set)
    children: dict[str, set[str]] = defaultdict(set)
    rejected: list[dict[str, Any]] = []
    duplicate_count = 0
    conflict_count = 0
    containment_count = 0

    for left_index, left in enumerate(candidates):
        for right in candidates[left_index + 1 :]:
            if not left.bbox or not right.bbox:
                continue
            if _is_rendered_page_image(left) or _is_rendered_page_image(right):
                continue
            intersection = _bbox_intersection_area(left.bbox, right.bbox)
            if intersection <= 0:
                continue
            left_area = _bbox_area(left.bbox)
            right_area = _bbox_area(right.bbox)
            if left_area <= 0 or right_area <= 0:
                continue
            min_cover = intersection / max(min(left_area, right_area), 1.0)
            iou = intersection / max(left_area + right_area - intersection, 1.0)

            if min_cover >= 0.92 and abs(left_area - right_area) > 1.0:
                parent, child = (left, right) if left_area > right_area else (right, left)
                parents[child.candidate_id].add(parent.candidate_id)
                children[parent.candidate_id].add(child.candidate_id)
                containment_count += 1

            if left.kind == right.kind and iou >= 0.9:
                winner, loser = _winner_loser(left, right)
                competing[left.candidate_id].add(right.candidate_id)
                competing[right.candidate_id].add(left.candidate_id)
                duplicate_count += 1
                rejected.append(
                    {
                        "candidate_id": loser.candidate_id,
                        "candidate_region_id": loser.selected_region_id,
                        "reason": "duplicate_lower_confidence_candidate",
                        "winner_candidate_id": winner.candidate_id,
                        "winner_region_id": winner.selected_region_id,
                        "iou": round(iou, 4),
                    }
                )
            elif iou >= 0.65 and not (_is_overlay_candidate(left) or _is_overlay_candidate(right)):
                competing[left.candidate_id].add(right.candidate_id)
                competing[right.candidate_id].add(left.candidate_id)
                conflict_count += 1
                rejected.append(
                    {
                        "candidate_id": _lower_confidence_candidate(left, right).candidate_id,
                        "candidate_region_id": _lower_confidence_candidate(left, right).selected_region_id,
                        "reason": "conflicting_overlap_candidate",
                        "other_candidate_id": _higher_confidence_candidate(left, right).candidate_id,
                        "other_region_id": _higher_confidence_candidate(left, right).selected_region_id,
                        "iou": round(iou, 4),
                    }
                )

    enriched = [
        replace(
            candidate,
            competing_candidate_ids=sorted(competing.get(candidate.candidate_id, set())),
            parent_candidate_ids=sorted(parents.get(candidate.candidate_id, set())),
            child_candidate_ids=sorted(children.get(candidate.candidate_id, set())),
        )
        for candidate in candidates
    ]
    return (
        enriched,
        rejected,
        {
            "duplicate_candidate_count": duplicate_count,
            "conflict_candidate_count": conflict_count,
            "containment_relation_count": containment_count,
        },
    )


def _winner_loser(left: RegionCandidate, right: RegionCandidate) -> tuple[RegionCandidate, RegionCandidate]:
    left_score = (left.confidence, len(left.evidence_ids), left.candidate_id)
    right_score = (right.confidence, len(right.evidence_ids), right.candidate_id)
    if left_score >= right_score:
        return left, right
    return right, left


def _higher_confidence_candidate(left: RegionCandidate, right: RegionCandidate) -> RegionCandidate:
    return _winner_loser(left, right)[0]


def _lower_confidence_candidate(left: RegionCandidate, right: RegionCandidate) -> RegionCandidate:
    return _winner_loser(left, right)[1]


def _is_overlay_candidate(candidate: RegionCandidate) -> bool:
    return candidate.kind in {"seal", "signature"} or candidate.role_hint in {"seal", "signature"}


def _is_rendered_page_image(candidate: RegionCandidate) -> bool:
    return candidate.kind == "image" and candidate.role_hint in {"rendered_image", "page_background", "vector_graphics"}


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
