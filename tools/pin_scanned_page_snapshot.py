#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pin OCR lines/tokens for a PDF page into a JSON fixture (L3 snapshot)."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _token_to_dict(token: object) -> dict:
    data = asdict(token) if hasattr(token, "__dataclass_fields__") else dict(token)  # type: ignore[arg-type]
    bbox = data.get("bbox")
    if bbox is not None:
        data["bbox"] = [float(v) for v in bbox]
    raw_bbox = data.get("raw_bbox")
    if raw_bbox is not None:
        data["raw_bbox"] = [float(v) for v in raw_bbox]
    data["page"] = int(data.get("page") or 0)
    data["confidence"] = float(data.get("confidence") or 1.0)
    data["coordinate_system"] = "pdf_points_top_left"
    return data


def pin_page_snapshot(
    pdf_path: Path,
    *,
    page_index: int,
    output_path: Path,
    source_run: str | None = None,
) -> dict:
    import fitz

    from tests._scanned_ocr_helpers import ocr_page_as_pdf_points

    with fitz.open(pdf_path) as doc:
        page = doc[page_index]
        page_width = float(page.rect.width)
        page_height = float(page.rect.height)
        ocr, lines, tokens = ocr_page_as_pdf_points(page, page_index)

    payload = {
        "page": page_index + 1,
        "page_width": page_width,
        "page_height": page_height,
        "source_pdf": str(pdf_path.relative_to(REPO_ROOT)) if pdf_path.is_relative_to(REPO_ROOT) else str(pdf_path),
        "source_run": source_run,
        "lines": [
            {
                "content": line["content"],
                "bbox": [float(v) for v in line["bbox"]],
                "confidence": float(line.get("confidence") or 1.0),
            }
            for line in lines
        ],
        "tokens": [_token_to_dict(token) for token in tokens],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="Path to source PDF")
    parser.add_argument("--page-index", type=int, default=3, help="0-based page index (default: 3 = page 4)")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "tests/fixtures/scanned/account_card_page4_full_layout.json",
        help="Output JSON path",
    )
    parser.add_argument("--source-run", type=str, default=None, help="Optional output run id for audit")
    args = parser.parse_args()

    payload = pin_page_snapshot(
        args.pdf.resolve(),
        page_index=args.page_index,
        output_path=args.output.resolve(),
        source_run=args.source_run,
    )
    print(f"Wrote {args.output} ({len(payload['lines'])} lines, {len(payload['tokens'])} tokens)")


if __name__ == "__main__":
    main()
