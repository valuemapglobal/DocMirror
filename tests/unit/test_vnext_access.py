# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from docmirror.models.mirror.page_access import (
    field_grid_structures_from_document,
    get_page_projection,
    micro_grid_structures_from_document,
    page_flow_texts,
    resolve_block,
)
from docmirror.models.mirror.vnext_access import (
    get_page,
    iter_blocks,
    iter_evidence,
    iter_regions,
    iter_structures,
    resolve_ref,
)


def _document() -> dict:
    return {
        "pages": [
            {
                "page_number": 1,
                "regions": [
                    {
                        "region_id": "r_micro",
                        "kind": "micro_grid",
                        "structure": {"grid_id": "mg_1", "rows": 2},
                    },
                    {
                        "region_id": "r_field",
                        "kind": "field_grid",
                        "structure": {"field_id": "fg_1"},
                    },
                ],
                "blocks": [
                    {"id": "b1", "type": "text", "role": "body", "ref": "region:r_micro", "morphology": "grid"}
                ],
                "flow": {
                    "texts": [{"content": "hello", "evidence_ids": ["ev_text"]}],
                    "key_values": [{"key": "name", "value": "DocMirror"}],
                },
                "tables": [{"table_id": "t1", "rows": []}],
            }
        ],
        "evidence": {"atoms": [{"id": "ev_text", "kind": "text", "page": 1, "text": "hello"}]},
    }


def test_vnext_access_reads_pages_regions_blocks_structures_and_evidence() -> None:
    doc = _document()

    assert get_page(doc, 1)["page_number"] == 1
    assert [region["region_id"] for region in iter_regions(doc, kind="micro_grid")] == ["r_micro"]
    assert [block["id"] for block in iter_blocks(doc, page=1, morphology="grid")] == ["b1"]
    assert list(iter_structures(doc, page=1, kind="field_grid")) == [{"field_id": "fg_1"}]
    assert [item["id"] for item in iter_evidence(doc, page=1, kind="text")] == ["ev_text"]
    assert resolve_ref(doc, 1, "region:r_micro")["kind"] == "micro_grid"
    assert resolve_ref(doc, 1, "text:0")["content"] == "hello"
    assert resolve_ref(doc, 1, "kv:0")["value"] == "DocMirror"
    assert resolve_ref(doc, 1, "table:t1")["table_id"] == "t1"


def test_page_access_prefers_vnext_structures() -> None:
    doc = _document()

    assert get_page_projection(doc, 1)["page_number"] == 1
    assert micro_grid_structures_from_document(doc) == [{"grid_id": "mg_1", "rows": 2}]
    assert field_grid_structures_from_document(doc, page=1) == [{"field_id": "fg_1"}]
    assert page_flow_texts(doc, 1) == [{"content": "hello", "evidence_ids": ["ev_text"]}]
    assert resolve_block(doc, 1, {"ref": "region:r_micro"})["region_id"] == "r_micro"


def test_page_access_does_not_read_removed_document_fields() -> None:
    doc = {"micro_grids": [{"grid_id": "removed_mg"}], "pages": [{"page_number": 1, "texts": [{"content": "raw"}]}]}

    assert micro_grid_structures_from_document(doc) == []
    assert page_flow_texts(doc, 1) == []
