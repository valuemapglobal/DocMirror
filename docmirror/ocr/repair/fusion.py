# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Candidate fusion for local OCR repair."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from docmirror.evidence.repair import RepairCandidate

_SPACE_RE = re.compile(r"\s+")


def normalize_candidate_text(text: str) -> str:
    return _SPACE_RE.sub("", str(text or "")).strip()


def fuse_text_candidates(
    raw_candidates: list[dict[str, Any]],
    *,
    request_id: str,
    min_confidence: float = 0.35,
) -> list[RepairCandidate]:
    """Fuse OCR outputs by normalized text consensus."""
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in raw_candidates:
        text = str(candidate.get("text") or "").strip()
        confidence = _float(candidate.get("confidence"))
        key = normalize_candidate_text(text)
        if not key or confidence < min_confidence:
            continue
        buckets[key].append(candidate)

    fused: list[RepairCandidate] = []
    for index, (key, members) in enumerate(buckets.items(), start=1):
        best = max(members, key=lambda item: _float(item.get("confidence")))
        mean_confidence = sum(_float(item.get("confidence")) for item in members) / len(members)
        consensus_bonus = min(0.2, 0.05 * (len({str(item.get("source") or "") for item in members}) - 1))
        confidence = min(1.0, mean_confidence + consensus_bonus)
        fused.append(
            RepairCandidate(
                candidate_id=f"{request_id}:cand:{index:04d}",
                request_id=request_id,
                text=str(best.get("text") or key),
                confidence=round(confidence, 4),
                source="ocr_repair_fusion",
                provenance={
                    "normalized_text": key,
                    "member_count": len(members),
                    "sources": sorted({str(item.get("source") or "") for item in members}),
                    "best": dict(best),
                    "members": members,
                },
            )
        )

    return sorted(fused, key=lambda item: (item.confidence, len(item.text)), reverse=True)


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


__all__ = ["fuse_text_candidates", "normalize_candidate_text"]
