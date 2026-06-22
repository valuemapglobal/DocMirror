#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Design 19 G5 / C2 — PCM mirror JSON byte-count gates."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "tests/fixtures/golden/pcm_mirror_volume_baseline.json"


def _synthetic_parse_result():
    from docmirror.core.ocr.page_canvas.evidence_bundles import domain_specific_with_page_bundles, page_evidence_bundle
    from docmirror.models.entities.parse_result import DocumentEntities, PageContent, ParseResult

    page = 4
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


def _legacy_inline_forensic_payload(pr) -> dict:
    """Simulate pre-PCM forensic with duplicated inline OCR in evidence sidecars."""
    api = copy.deepcopy(pr.to_api_dict(mirror_level="forensic", include_text=False))
    doc = api["data"]["document"]
    pool = {
        int(item.get("page") or 0): item
        for item in (doc.get("scanned_ocr_pages") or [])
        if isinstance(item, dict)
    }
    for key in ("scanned_micro_grid_evidence", "scanned_local_structure_evidence"):
        for evidence in doc.get(key) or []:
            if not isinstance(evidence, dict):
                continue
            page_num = int(evidence.get("page") or 0)
            pool_item = pool.get(page_num)
            if pool_item:
                evidence["lines"] = copy.deepcopy(pool_item.get("lines") or [])
                evidence["tokens"] = copy.deepcopy(pool_item.get("tokens") or [])
    for page in doc.get("pages") or []:
        if not isinstance(page, dict):
            continue
        for region in page.get("regions") or []:
            if not isinstance(region, dict) or region.get("kind") != "field_grid":
                continue
            structure = region.get("structure")
            if isinstance(structure, dict):
                for evidence in doc.get("scanned_local_structure_evidence") or []:
                    if int(evidence.get("page") or 0) == int(page.get("page_number") or 0):
                        evidence["structures"] = [copy.deepcopy(structure)]
                        break
    return api


def measure() -> dict[str, int]:
    pr = _synthetic_parse_result()
    pcm_forensic = _payload_bytes(pr.to_api_dict(mirror_level="forensic", include_text=False))
    pcm_standard = _payload_bytes(pr.to_api_dict(mirror_level="standard", include_text=False))
    legacy_forensic = _payload_bytes(_legacy_inline_forensic_payload(pr))
    return {
        "legacy_inline_forensic_bytes": legacy_forensic,
        "pcm_forensic_bytes": pcm_forensic,
        "pcm_standard_bytes": pcm_standard,
    }


def main() -> int:
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    measured = measure()
    legacy = measured["legacy_inline_forensic_bytes"]
    pcm_forensic = measured["pcm_forensic_bytes"]
    pcm_standard = measured["pcm_standard_bytes"]

    if legacy <= 0:
        print("PCM mirror volume gate FAILED: legacy baseline is zero", file=sys.stderr)
        return 1

    reduction = (legacy - pcm_forensic) / legacy
    min_reduction = float(baseline.get("forensic_reduction_min_ratio", 0.30))
    if reduction + 1e-9 < min_reduction:
        print(
            f"PCM mirror volume gate FAILED (C2): forensic reduction {reduction:.1%} "
            f"< required {min_reduction:.0%} "
            f"(legacy={legacy}, pcm={pcm_forensic})",
            file=sys.stderr,
        )
        return 1

    max_standard = int(baseline["pcm_standard_bytes_max"])
    max_increase = float(baseline.get("standard_max_increase_ratio", 0.05))
    allowed_standard = int(max_standard * (1.0 + max_increase))
    if pcm_standard > allowed_standard:
        print(
            f"PCM mirror volume gate FAILED (G5): standard bytes {pcm_standard} "
            f"> allowed {allowed_standard} (baseline max {max_standard} + {max_increase:.0%})",
            file=sys.stderr,
        )
        return 1

    print(
        "PCM mirror volume gate OK "
        f"(C2 forensic −{reduction:.1%}, G5 standard {pcm_standard} ≤ {allowed_standard})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
