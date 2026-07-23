#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Design 19 G5 / C2 — PageProjection mirror JSON byte-count gates."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _synthetic_parse_result():
    from docmirror.models.entities.parse_result import DocumentEntities, PageContent, ParseResult
    from docmirror.models.mirror.page_evidence_bundles import (
        domain_specific_with_page_bundles,
        page_evidence_bundle,
    )

    page = 4
    lines = [{"content": f"line-{i}", "bbox": [1, i, 10, i + 1], "confidence": 0.9} for i in range(200)]
    tokens = [{"text": f"t{i}", "bbox": [1, i, 2, i + 1], "confidence": 0.9, "line_id": f"l{i}"} for i in range(800)]
    evidence = {
        "page": page,
        "page_width": 800.0,
        "page_height": 600.0,
        "lines": lines,
        "tokens": tokens,
    }
    bundle = page_evidence_bundle(
        page,
        page_width=800.0,
        page_height=600.0,
        micro_grid_evidence=evidence,
        local_structure_evidence=dict(evidence),
    )
    return ParseResult(
        pages=[PageContent(page_number=page, width=800, height=600)],
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=domain_specific_with_page_bundles(bundle),
        ),
    )


def _payload_bytes(payload: dict) -> int:
    return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def measure() -> dict[str, int]:
    from docmirror.models.sealed import seal_parse_result
    from docmirror.output.mirror_projector import project_mirror

    pr = _synthetic_parse_result()
    mirror = project_mirror(seal_parse_result(pr))
    vnext_forensic = _payload_bytes(mirror)
    vnext_standard = _payload_bytes(mirror)
    return {
        "vnext_forensic_bytes": vnext_forensic,
        "vnext_standard_bytes": vnext_standard,
        "top_level_section_count": len(
            [
                key
                for key in ("mirror", "source", "document", "pages", "evidence", "regions", "blocks", "graph")
                if key in mirror
            ]
        ),
    }


def main() -> int:
    measured = measure()
    vnext_forensic = measured["vnext_forensic_bytes"]
    vnext_standard = measured["vnext_standard_bytes"]

    if vnext_forensic <= 0:
        print("PageProjection mirror volume gate FAILED: vNext forensic payload is zero", file=sys.stderr)
        return 1

    if measured["top_level_section_count"] < 8:
        print(
            "PageProjection mirror volume gate FAILED: vNext mirror is missing required top-level sections",
            file=sys.stderr,
        )
        return 1

    print(f"PageProjection mirror volume gate OK (vNext forensic {vnext_forensic}, standard {vnext_standard})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
