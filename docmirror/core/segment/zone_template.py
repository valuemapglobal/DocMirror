# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Zone template — cross-page zone layout replay.

Purpose: Builds and applies ``ZoneTemplate`` from a reference page so
subsequent pages inherit consistent column/table geometry (ledger statements).

Main components: ``build_zone_template``, ``apply_zone_template``.

Upstream: First-page zones, ``extraction_profile``.

Downstream: ``segment.zone_segment``, ``extract.template_injector``.
"""

from __future__ import annotations

import logging

from docmirror.core.segment.zone_models import Zone, ZoneTemplate

logger = logging.getLogger(__name__)

def build_zone_template(zones: list[Zone], page_w: float, page_h: float, page_idx: int = 0) -> ZoneTemplate:
    """Build a reusable zone template from a fully-segmented page.

    Captures the zone types and their normalized bbox positions.
    Called once on page 0, result reused for pages 1~N.

    Args:
        zones: Zone list from segment_page_into_zones.
        page_w: Page width in points.
        page_h: Page height in points.
        page_idx: Source page index.

    Returns:
        ZoneTemplate with normalized coordinates.
    """
    template_zones = []
    for z in zones:
        x0, y0, x1, y1 = z.bbox
        bbox_ratio = (
            x0 / max(page_w, 1),
            y0 / max(page_h, 1),
            x1 / max(page_w, 1),
            y1 / max(page_h, 1),
        )
        template_zones.append((z.type, bbox_ratio, z.confidence))

    return ZoneTemplate(
        zones=template_zones,
        source_page=page_idx,
        zone_count=len(template_zones),
    )


def apply_zone_template(
    template: ZoneTemplate,
    page_plum,
    page_idx: int,
) -> list[Zone] | None:
    """Apply a cached zone template to a new page, skipping full segmentation.

    Maps the template's normalized bboxes onto the new page dimensions,
    then assigns each character to the zone whose bbox contains it.

    Safety: If fewer than 50% of chars are captured by template zones,
    returns None (caller should fall back to full segmentation).

    Args:
        template: ZoneTemplate from build_zone_template.
        page_plum: pdfplumber page object.
        page_idx: Current page index.

    Returns:
        list[Zone] if template applied successfully, None if fallback needed.
    """
    chars = page_plum.chars
    rects = page_plum.rects or []
    page_h = page_plum.height
    page_w = page_plum.width

    if not chars or not template.zones:
        return None

    # Project template bboxes onto this page's dimensions
    projected_zones = []
    for zone_type, bbox_ratio, confidence in template.zones:
        rx0, ry0, rx1, ry1 = bbox_ratio
        bbox = (
            rx0 * page_w,
            ry0 * page_h,
            rx1 * page_w,
            ry1 * page_h,
        )
        projected_zones.append(
            {
                "type": zone_type,
                "bbox": bbox,
                "confidence": confidence,
                "chars": [],
                "rects": [],
            }
        )

    # Assign each char to the closest containing zone
    assigned_count = 0
    for c in chars:
        cx = (c.get("x0", 0) + c.get("x1", 0)) / 2
        cy = (c.get("top", 0) + c.get("bottom", 0)) / 2
        best_zone = None
        best_dist = float("inf")

        for pz in projected_zones:
            bx0, by0, bx1, by1 = pz["bbox"]
            margin = 3.0
            if bx0 - margin <= cx <= bx1 + margin and by0 - margin <= cy <= by1 + margin:
                best_zone = pz
                break
            else:
                zcx = (bx0 + bx1) / 2
                zcy = (by0 + by1) / 2
                dist = abs(cx - zcx) + abs(cy - zcy)
                if dist < best_dist:
                    best_dist = dist
                    best_zone = pz

        if best_zone is not None:
            best_zone["chars"].append(c)
            assigned_count += 1

    if assigned_count < len(chars) * 0.5:
        logger.debug(
            f"[DocMirror] Perf #9: template mismatch on page {page_idx} "
            f"({assigned_count}/{len(chars)} chars assigned), falling back"
        )
        return None

    for r in rects:
        ry = r.get("top", 0)
        for pz in projected_zones:
            bx0, by0, bx1, by1 = pz["bbox"]
            if by0 - 3 <= ry <= by1 + 3:
                pz["rects"].append(r)
                break

    result_zones = []
    for pz in projected_zones:
        if not pz["chars"]:
            continue

        zone_chars = sorted(pz["chars"], key=lambda c: (c["top"], c["x0"]))
        text = "".join(c["text"] for c in zone_chars)

        actual_x0 = min(c["x0"] for c in zone_chars)
        actual_y0 = min(c["top"] for c in zone_chars)
        actual_x1 = max(c["x1"] for c in zone_chars)
        actual_y1 = max(c["bottom"] for c in zone_chars)

        zone = Zone(
            type=pz["type"],
            bbox=(actual_x0, actual_y0, actual_x1, actual_y1),
            page=page_idx,
            chars=list(pz["chars"]),
            rects=list(pz["rects"]),
            text=text.strip(),
            confidence=pz["confidence"],
        )
        result_zones.append(zone)

    logger.debug(
        f"[DocMirror] Perf #9: template applied on page {page_idx} → "
        f"{len(result_zones)} zones ({assigned_count}/{len(chars)} chars)"
    )
    return result_zones
