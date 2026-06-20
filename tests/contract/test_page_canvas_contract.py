# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

import pytest

from docmirror.core.ocr.local_structure import extract_local_structure_evidence
from docmirror.core.ocr.page_canvas.evidence_bundles import domain_specific_with_page_bundles, page_evidence_bundle
from docmirror.models.entities.parse_result import DocumentEntities, PageContent, ParseResult, TextBlock, TextLevel
from docmirror.models.mirror.legacy_project import fold_legacy_mirror_document
from docmirror.models.mirror.page_access import iter_page_regions

_FIXTURE = Path("tests/fixtures/scanned/account_card_page4_full_layout.json")
_MIRROR_SAMPLE = Path("output/20260618_133532_41c1/001_mirror.json")


def _load_fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def test_fold_full_page_fixture_produces_field_grid_regions():
    fixture = _load_fixture()
    lines = [
        {"content": line["content"], "bbox": line["bbox"], "confidence": line.get("confidence", 1.0)}
        for line in fixture["lines"]
    ]
    evidence = extract_local_structure_evidence(
        lines,
        tokens=fixture["tokens"],
        page=4,
        page_width=fixture["page_width"],
        page_height=fixture["page_height"],
    )
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=domain_specific_with_page_bundles(
                page_evidence_bundle(
                    4,
                    page_width=fixture["page_width"],
                    page_height=fixture["page_height"],
                    local_structure_evidence={
                        "page": 4,
                        "page_width": fixture["page_width"],
                        "page_height": fixture["page_height"],
                        "structures": evidence.get("structures") or [],
                    },
                ),
            ),
        ),
        pages=[PageContent(page_number=4, width=int(fixture["page_width"]), height=int(fixture["page_height"]))],
    )
    api = pr.to_api_dict(mirror_level="standard")
    doc = api["data"]["document"]
    regions = list(iter_page_regions(doc, 4))
    assert len(regions) >= 3
    kinds = {r.get("kind") for r in regions}
    assert "field_grid" in kinds


@pytest.mark.skipif(not _MIRROR_SAMPLE.exists(), reason="sample mirror output not available")
def test_fold_legacy_mirror_json_micro_grid_parity():
    payload = json.loads(_MIRROR_SAMPLE.read_text(encoding="utf-8"))
    document = (payload.get("data") or {}).get("document") or {}
    legacy_grids = [g for g in (document.get("micro_grids") or []) if int(g.get("page") or 0) == 4]
    folded = fold_legacy_mirror_document(document)
    page4 = next(p for p in folded["pages"] if int(p.get("page_number") or 0) == 4)
    grid_regions = [r for r in page4.get("regions") or [] if r.get("kind") == "micro_grid"]
    assert len(grid_regions) >= len(legacy_grids) or len(legacy_grids) == 0


def test_api_page_flow_shape():
    pr = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                texts=[TextBlock(content="line", level=TextLevel.BODY)],
            )
        ],
    )
    api = pr.to_api_dict(mirror_level="standard")
    page = api["data"]["document"]["pages"][0]
    assert page["flow"]["texts"][0]["content"] == "line"
    assert "texts" not in page
