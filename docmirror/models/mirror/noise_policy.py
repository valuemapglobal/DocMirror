# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NoisePolicyEngine — repeated header/footer detection and profile-based suppression.

Profiles:
  - human_default: suppress header/footer/watermark
  - rag_default: suppress header/footer/watermark, keep page numbers as metadata
  - forensic: preserve all, annotate role
  - layout_debug: preserve all, output suppression reasons
"""

from __future__ import annotations

from typing import Any


def detect_repeated_noise(
    pages: list[dict[str, Any]],
    *,
    profile: str = "human_default",
) -> list[dict[str, Any]]:
    """Detect repeated header/footer/watermark across pages.

    Args:
        pages: List of page dicts from _build_api_pages or similar.
        profile: Noise suppression profile.

    Returns:
        List of noise entries with type, pages, policy, and text sample.
    """
    noise_entries: list[dict[str, Any]] = []
    if profile == "layout_debug":
        return _collect_all_noise(pages)

    # Collect all texts with header/footer/watermark roles
    header_texts: dict[str, list[dict[str, Any]]] = {}
    footer_texts: dict[str, list[dict[str, Any]]] = {}
    watermark_texts: dict[str, list[dict[str, Any]]] = {}

    for page in pages:
        page_no = int(page.get("page_number") or 0)
        for text in page.get("texts") or []:
            if not isinstance(text, dict):
                continue
            role = str(text.get("mirror_role") or text.get("level") or "").lower()
            content = str(text.get("content") or "").strip()
            if not content:
                continue

            if role == "header":
                header_texts.setdefault(content, []).append(
                    {
                        "page": page_no,
                        "text": content,
                        "bbox": text.get("bbox"),
                        "evidence_ids": text.get("evidence_ids") or [],
                    }
                )
            elif role == "footer":
                footer_texts.setdefault(content, []).append(
                    {
                        "page": page_no,
                        "text": content,
                        "bbox": text.get("bbox"),
                        "evidence_ids": text.get("evidence_ids") or [],
                    }
                )
            elif role == "watermark":
                watermark_texts.setdefault(content, []).append(
                    {
                        "page": page_no,
                        "text": content,
                        "bbox": text.get("bbox"),
                        "evidence_ids": text.get("evidence_ids") or [],
                    }
                )

    # Repeated noise: same content on multiple pages
    for noise_type, noise_dict in [
        ("header", header_texts),
        ("footer", footer_texts),
        ("watermark", watermark_texts),
    ]:
        for text_content, occurrences in noise_dict.items():
            pages_list = sorted(set(o["page"] for o in occurrences))
            if len(pages_list) >= 2 or noise_type == "watermark":
                # Repeated or watermark — suppress in human/rag profiles
                policy = "excluded_from_markdown"
                noise_entries.append(
                    {
                        "type": noise_type,
                        "pages": pages_list,
                        "policy": policy,
                        "evidence_refs": list(set(eid for o in occurrences for eid in o.get("evidence_ids", []))),
                        "text_sample": text_content[:200],
                        "occurrence_count": len(occurrences),
                    }
                )

    # Single-occurrence header/footer: only suppress if at page boundary
    for noise_type, noise_dict in [
        ("header", header_texts),
        ("footer", footer_texts),
    ]:
        for text_content, occurrences in noise_dict.items():
            if len(occurrences) < 2:
                pages_list = sorted(set(o["page"] for o in occurrences))
                occ = occurrences[0]
                bbox = occ.get("bbox")
                # Check if near page top (header) or page bottom (footer)
                if noise_type == "header" and _is_near_page_top(bbox):
                    noise_entries.append(
                        {
                            "type": "header",
                            "pages": pages_list,
                            "policy": "excluded_from_markdown",
                            "evidence_refs": occ.get("evidence_ids", []),
                            "text_sample": text_content[:200],
                            "occurrence_count": 1,
                        }
                    )
                elif noise_type == "footer" and _is_near_page_bottom(bbox):
                    noise_entries.append(
                        {
                            "type": "footer",
                            "pages": pages_list,
                            "policy": "excluded_from_markdown",
                            "evidence_refs": occ.get("evidence_ids", []),
                            "text_sample": text_content[:200],
                            "occurrence_count": 1,
                        }
                    )

    return noise_entries


def _is_near_page_top(bbox: Any, threshold: float = 120.0) -> bool:
    """Check if bbox is near the top of the page."""
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 2:
        return float(bbox[1]) < threshold
    return False


def _is_near_page_bottom(bbox: Any, threshold: float = 700.0) -> bool:
    """Check if bbox is near the bottom of the page."""
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        return float(bbox[3]) > threshold
    return False


def _collect_all_noise(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collect all noise annotations for layout_debug profile."""
    entries: list[dict[str, Any]] = []
    for page in pages:
        page_no = int(page.get("page_number") or 0)
        for text in page.get("texts") or []:
            if not isinstance(text, dict):
                continue
            role = str(text.get("mirror_role") or text.get("level") or "").lower()
            if role in ("header", "footer", "watermark"):
                entries.append(
                    {
                        "type": role,
                        "pages": [page_no],
                        "policy": "preserved_for_debug",
                        "text_sample": str(text.get("content") or "")[:200],
                        "reason": f"role={role}",
                    }
                )
    return entries


__all__ = [
    "detect_repeated_noise",
]
