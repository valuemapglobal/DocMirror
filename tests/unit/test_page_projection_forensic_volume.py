# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json

from docmirror.models.entities.parse_result import DocumentEntities, PageContent, ParseResult
from docmirror.models.mirror.page_evidence_bundles import domain_specific_with_page_bundles, page_evidence_bundle


def _large_bundle(page: int = 4) -> dict:
    lines = [{"content": f"line-{i}", "bbox": [1, i, 10, i + 1], "confidence": 0.9} for i in range(200)]
    tokens = [
        {"text": f"t{i}", "bbox": [1, i, 2, i + 1], "confidence": 0.9, "line_id": f"l{i}"}
        for i in range(800)
    ]
    evidence = {
        "page": page,
        "page_width": 800.0,
        "page_height": 600.0,
        "lines": lines,
        "tokens": tokens,
    }
    return page_evidence_bundle(
        page,
        page_width=800.0,
        page_height=600.0,
        micro_grid_evidence=evidence,
        local_structure_evidence=dict(evidence),
    )


def test_forensic_mirror_strips_inline_ocr_from_evidence():
    pr = ParseResult(
        pages=[PageContent(page_number=4, width=800, height=600)],
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=domain_specific_with_page_bundles(_large_bundle()),
        ),
    )
    api = pr.to_mirror_json_vnext(mirror_level="forensic", include_text=False)
    payload = json.dumps(api, ensure_ascii=False)
    doc = api
    smg = doc.get("scanned_micro_grid_evidence") or []
    assert smg and "lines" not in smg[0] and "tokens" not in smg[0]
    assert doc.get("scanned_ocr_pages")
    assert len(payload) < 120_000
