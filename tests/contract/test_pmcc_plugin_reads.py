# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""PMCC contract — plugins read Mirror via page_access (Design 20 Phase 3)."""

from __future__ import annotations

from docmirror.core.ocr.page_canvas.evidence_bundles import merge_micro_grid_structures_into_bundles
from docmirror.models.entities.parse_result import DocumentEntities, PageContent, ParseResult
from docmirror.models.mirror.page_access import (
    get_page_canvas,
    iter_page_blocks,
    resolve_block_ref,
)
from docmirror.plugins._base.generic_mirror_adapter import (
    _collect_structure_projected_records,
    build_generic_community_output,
)


def test_page_access_resolves_all_block_refs():
    api_page = {
        "page_number": 1,
        "flow": {"texts": [{"content": "hdr"}], "key_values": [{"key": "k", "value": "v"}]},
        "tables": [{"table_id": "pt_1_0", "headers": ["A"]}],
        "regions": [{"region_id": "rg_x", "structure": {"cells": []}}],
        "blocks": [
            {"ref": "text:0"},
            {"ref": "kv:0"},
            {"ref": "table:pt_1_0"},
            {"ref": "region:rg_x"},
        ],
    }
    doc = {"pages": [api_page]}
    for block in iter_page_blocks(doc, 1):
        assert resolve_block_ref(api_page, block["ref"]) is not None


def test_generic_collects_structure_projected_records():
    grid = {
        "grid_id": "mg_p4_0",
        "page": 4,
        "bbox": [0, 10, 100, 50],
        "anchor_text": "anchor",
        "confidence": 0.8,
        "cells": [[{"text": "2021-01", "role": "month"}]],
        "row_bands": [[]],
    }
    ds: dict = {}
    merge_micro_grid_structures_into_bundles(ds, [grid])
    pr = ParseResult(
        pages=[PageContent(page_number=4, width=100, height=200)],
        entities=DocumentEntities(document_type="unknown_report", domain_specific=ds),
    )
    projected = _collect_structure_projected_records(pr)
    assert projected
    out = build_generic_community_output(pr, "unknown_report")
    data = out.get("data") or {}
    records = data.get("records") or []
    struct_recs = data.get("structure_projected_records") or []
    assert records or struct_recs


def test_get_page_canvas_blocks_present_after_api_dict():
    grid = {
        "grid_id": "mg_p4_0",
        "page": 4,
        "bbox": [0, 10, 100, 50],
        "confidence": 0.8,
        "cells": [],
    }
    ds: dict = {}
    merge_micro_grid_structures_into_bundles(ds, [grid])
    pr = ParseResult(
        pages=[PageContent(page_number=4, width=100, height=200)],
        entities=DocumentEntities(document_type="credit_report", domain_specific=ds),
    )
    api = pr.to_api_dict(mirror_level="standard")
    doc = api["data"]["document"]
    page = get_page_canvas(doc, 4)
    assert page is not None
    assert "blocks" in page
    assert len(page["blocks"]) >= 1
