# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

from docmirror.core.ocr.page_canvas.build import (
    build_page_regions_for_page,
    region_from_micro_grid,
)
from docmirror.core.ocr.page_canvas.evidence_bundles import merge_micro_grid_structures_into_bundles
from docmirror.core.ocr.page_canvas.models import PageCanvas, PageFlow, PageRegion
from docmirror.models.entities.parse_result import DocumentEntities, PageContent, ParseResult, TextBlock, TextLevel
from docmirror.models.mirror.legacy_project import enrich_api_page_with_canvas, fold_legacy_mirror_document
from docmirror.models.mirror.page_access import (
    find_region_by_id,
    get_page_canvas,
    iter_page_regions,
    micro_grids_from_document,
)
from docmirror.models.mirror.page_canvas_export import enrich_api_pages_with_page_canvas


def test_page_region_roundtrip():
    grid = {
        "grid_id": "mg_p4_repayment_0",
        "page": 4,
        "bbox": [10.0, 20.0, 100.0, 80.0],
        "anchor_text": "2020年09月-2021年02月的还款记录",
        "confidence": 0.82,
        "cells": [],
    }
    region = region_from_micro_grid(grid)
    assert region is not None
    assert region.region_id == "rg_p4_repayment_0"
    assert region.kind == "micro_grid"
    assert region.morphology == "S3"
    d = region.to_dict()
    assert d["structure"]["grid_id"] == "mg_p4_repayment_0"


def test_build_page_regions_for_page():
    grid = {
        "grid_id": "mg_p4_repayment_0",
        "page": 4,
        "bbox": [1, 2, 3, 4],
        "anchor_text": "anchor",
        "confidence": 0.5,
    }
    structure = {
        "structure_id": "ls_p4_0",
        "structure_kind": "field_grid",
        "page": 4,
        "bbox": [5, 6, 7, 8],
        "anchors": ("账户2",),
        "confidence": 0.9,
        "cells": [{"cell_id": "c1", "text": "x"}],
    }
    regions = build_page_regions_for_page(
        4,
        micro_grids=[grid],
        local_structure_evidence=[{"page": 4, "structures": [structure]}],
    )
    assert len(regions) == 2
    kinds = {r.kind for r in regions}
    assert kinds == {"micro_grid", "field_grid"}


def test_page_canvas_to_dict():
    canvas = PageCanvas(
        page_number=4,
        width=100.0,
        height=200.0,
        flow=PageFlow(texts=[{"content": "hello"}]),
        regions=[
            PageRegion(
                region_id="rg_p4_repayment_0",
                kind="micro_grid",
                morphology="S3",
                bbox=[0, 0, 1, 1],
                structure={"grid_id": "mg_p4_repayment_0"},
            )
        ],
    )
    d = canvas.to_dict()
    assert d["page_number"] == 4
    assert d["flow"]["texts"][0]["content"] == "hello"
    assert d["regions"][0]["region_id"] == "rg_p4_repayment_0"


def test_parse_result_api_includes_page_regions():
    grid = {
        "grid_id": "mg_p4_repayment_0",
        "page": 4,
        "bbox": [1, 2, 3, 4],
        "anchor_text": "anchor",
        "confidence": 0.8,
        "cells": [[{"text": "N", "bbox": [1, 2, 3, 4], "row_index": 0, "col_index": 1}]],
    }
    ds: dict = {}
    merge_micro_grid_structures_into_bundles(ds, [grid])
    pr = ParseResult(
        pages=[],
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=ds,
        ),
    )
    pr.pages = [PageContent(page_number=4, width=100, height=200)]
    api = pr.to_api_dict(mirror_level="standard")
    doc = api["data"]["document"]
    page = get_page_canvas(doc, 4)
    assert page is not None
    regions = list(iter_page_regions(doc, 4))
    assert len(regions) == 1
    assert regions[0]["kind"] == "micro_grid"
    assert page.get("flow", {}).get("texts") is not None
    assert micro_grids_from_document(doc)


def test_page_access_find_region():
    doc = {
        "pages": [
            {
                "page_number": 4,
                "regions": [{"region_id": "rg_p4_repayment_0", "kind": "micro_grid", "structure": {}}],
            }
        ]
    }
    found = find_region_by_id(doc, "rg_p4_repayment_0")
    assert found == (4, doc["pages"][0]["regions"][0])


def test_pcm_mirror_omits_legacy_document_fields():
    grid = {
        "grid_id": "mg_p4_repayment_0",
        "page": 4,
        "bbox": [1, 2, 3, 4],
        "anchor_text": "anchor",
        "confidence": 0.8,
        "cells": [],
    }
    ds: dict = {}
    merge_micro_grid_structures_into_bundles(ds, [grid])
    pr = ParseResult(
        pages=[PageContent(page_number=4, width=100, height=200, texts=[TextBlock(content="line", level=TextLevel.BODY)])],
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=ds,
        ),
    )
    api = pr.to_api_dict(mirror_level="standard")
    doc = api["data"]["document"]
    assert "micro_grids" not in doc
    assert "_deprecated" not in doc
    assert list(iter_page_regions(doc, 4))
    assert "pcm_legacy_shim" not in api["meta"]
    page = get_page_canvas(doc, 4)
    assert page is not None
    assert page.get("flow", {}).get("texts")
    assert "texts" not in page


def test_domain_access_prefers_bundles_for_local_structure_evidence():
    from docmirror.core.ocr.page_canvas.evidence_bundles import (
        domain_specific_with_page_bundles,
        merge_micro_grid_structures_into_bundles,
        page_evidence_bundle,
    )
    from docmirror.models.mirror.domain_access import local_structure_evidence_pages_from_domain_specific

    ds = domain_specific_with_page_bundles(
        page_evidence_bundle(
            4,
            local_structure_evidence={
                "page": 4,
                "structures": [
                    {
                        "structure_id": "ls_p4_0",
                        "structure_kind": "field_grid",
                        "page": 4,
                        "bbox": [5, 6, 7, 8],
                        "anchors": ("账户2",),
                        "confidence": 0.9,
                        "cells": [],
                    }
                ],
            },
        ),
    )
    merge_micro_grid_structures_into_bundles(
        ds,
        [{"grid_id": "mg_p4_x", "page": 4, "bbox": [1, 2, 3, 4], "confidence": 0.5}],
    )
    pages = local_structure_evidence_pages_from_domain_specific(ds)
    assert len(pages) == 1
    assert pages[0]["structures"][0]["structure_id"] == "ls_p4_0"


def test_legacy_access_counter_on_micro_grids_fallback():
    from docmirror.models.mirror.legacy_access import legacy_access_counts, reset_legacy_access_counts

    reset_legacy_access_counts()
    doc = {"micro_grids": [{"grid_id": "mg_p1", "page": 1, "bbox": [0, 0, 1, 1]}]}
    assert micro_grids_from_document(doc)
    counts = legacy_access_counts()
    assert counts.get("document.micro_grids") == 1
    reset_legacy_access_counts()
