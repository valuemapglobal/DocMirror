# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Crop generator — evidence bounding-box crops from ParseResult.

Purpose: Crops field evidence regions and collects evidence spans for visual
verification of extracted entities.

Main components: ``generate_field_crops``, ``crop_evidence_bbox``,
``collect_evidence_spans_from_parse_result``.

Upstream: ``ParseResult`` blocks with evidence bboxes.

Downstream: Debug zip bundles, human QA review.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def crop_evidence_bbox(
    pdf_path: str | Path,
    page: int,
    bbox: tuple[float, float, float, float],
    *,
    dpi: int = 150,
    padding: float = 4.0,
) -> bytes | None:
    """Crop a PDF page region to PNG bytes."""
    try:
        import fitz
    except ImportError:
        logger.debug("[CropGenerator] PyMuPDF not available")
        return None

    path = Path(pdf_path)
    if not path.exists():
        return None

    x0, y0, x1, y1 = bbox
    x0, y0 = max(0, x0 - padding), max(0, y0 - padding)
    x1, y1 = x1 + padding, y1 + padding

    try:
        doc = fitz.open(str(path))
        page_idx = max(0, min(page - 1, len(doc) - 1))
        pg = doc[page_idx]
        rect = fitz.Rect(x0, y0, x1, y1)
        pix = pg.get_pixmap(clip=rect, dpi=dpi)
        data = pix.tobytes("png")
        doc.close()
        return data
    except Exception as exc:
        logger.debug("[CropGenerator] crop failed: %s", exc)
        return None


def generate_field_crops(
    pdf_path: str | Path,
    evidence_spans: list[Any],
    output_dir: str | Path,
) -> list[dict[str, Any]]:
    """Write PNG crops for evidence spans with bbox; return manifest entries."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []

    for span in evidence_spans:
        bbox = getattr(span, "bbox", None) or (span.get("bbox") if isinstance(span, dict) else None)
        page = getattr(span, "page", None) or (span.get("page") if isinstance(span, dict) else 1)
        span_id = getattr(span, "id", None) or (span.get("id") if isinstance(span, dict) else "unknown")
        if not bbox or len(bbox) < 4:
            continue
        png = crop_evidence_bbox(pdf_path, page, tuple(bbox[:4]))
        if not png:
            continue
        fname = f"{span_id}.png"
        (out / fname).write_bytes(png)
        manifest.append({"evidence_id": span_id, "page": page, "file": fname, "bbox": list(bbox[:4])})

    return manifest


def collect_evidence_spans_from_parse_result(result: Any) -> list[Any]:
    """Build EvidenceSpan list from mirror blocks that carry bbox (debug crops)."""
    from docmirror.models.entities.evidence import EvidenceSpan

    spans: list[EvidenceSpan] = []
    for page in getattr(result, "pages", []) or []:
        page_no = getattr(page, "page_number", 1) or 1
        for block in list(getattr(page, "texts", []) or []) + list(getattr(page, "tables", []) or []):
            bbox = getattr(block, "bbox", None)
            if not bbox or len(bbox) < 4:
                continue
            evidence_ids = list(getattr(block, "evidence_ids", []) or [])
            span_id = evidence_ids[0] if evidence_ids else f"block_p{page_no}_{len(spans)}"
            text = ""
            if hasattr(block, "content"):
                text = str(block.content or "")[:500]
            elif hasattr(block, "headers"):
                text = " ".join(str(h) for h in (block.headers or []) if h)[:500]
            spans.append(
                EvidenceSpan(
                    id=span_id,
                    page=page_no,
                    kind="rect",
                    text=text,
                    bbox=list(bbox[:4]),
                    source="layout_model",
                )
            )
    return spans
