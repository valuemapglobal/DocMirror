# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Universal Block Index (Design 20 Phase 0)."""

from __future__ import annotations

from docmirror.core.ocr.page_canvas.block_index import (
    build_page_blocks,
    morphology_summary_from_blocks,
    pcm_blocks_enabled,
    reading_order_from_blocks,
)
from docmirror.core.ocr.page_canvas.models import PageBlock, PageRegion
from docmirror.models.mirror.page_access import resolve_block_ref


def _region(region_id: str, *, y0: float, kind: str = "field_grid", morph: str = "S4") -> PageRegion:
    return PageRegion(
        region_id=region_id,
        kind=kind,
        morphology=morph,
        bbox=[10.0, y0, 200.0, y0 + 50.0],
        structure={"structure_id": region_id.replace("rg_", "ls_"), "structure_kind": kind},
        anchor_text=region_id,
        confidence=0.9,
    )


def test_build_page_blocks_credit_mixed():
    regions = [
        _region("rg_p4_repayment_0", y0=100.0, kind="micro_grid", morph="S3"),
        _region("rg_p4_account_1", y0=200.0),
    ]
    flow_texts = [{"content": "header", "bbox": [10, 50, 100, 70]}]
    blocks, summary, order = build_page_blocks(
        4,
        regions=regions,
        flow_texts=flow_texts,
        flow_key_values=[],
        tables=[],
    )
    assert len(blocks) == 3
    assert summary.get("S3") == 1
    assert summary.get("S4") == 1
    assert summary.get("S1") == 1
    region_refs = {b.ref for b in blocks if b.ref.startswith("region:")}
    assert region_refs == {"region:rg_p4_repayment_0", "region:rg_p4_account_1"}
    assert len(order) == 3
    assert order == reading_order_from_blocks(blocks)


def test_build_page_blocks_bank_table():
    tables = [
        {
            "table_id": "pt_1_0",
            "headers": ["交易时间", "收入金额"],
            "row_count": 10,
            "bbox": [48, 90, 560, 780],
        }
    ]
    flow_texts = [{"content": "账户交易明细", "bbox": [72, 48, 400, 72]}]
    blocks, summary, order = build_page_blocks(
        1,
        regions=[],
        flow_texts=flow_texts,
        tables=tables,
    )
    assert summary.get("S2") == 1
    assert summary.get("S1") == 1
    s2 = next(b for b in blocks if b.morphology == "S2")
    assert s2.ref == "table:pt_1_0"
    assert s2.schema_hint == "core.physical_table.ledger"
    assert len(order) == 2


def test_build_page_blocks_key_values():
    kvs = [{"key": "发票代码", "value": "123", "bbox": [10, 10, 100, 30]}]
    blocks, summary, _ = build_page_blocks(1, regions=[], flow_key_values=kvs)
    assert summary.get("S5") == 1
    assert blocks[0].ref == "kv:0"


def test_resolve_block_ref_all_morphologies():
    api_page = {
        "page_number": 1,
        "flow": {
            "texts": [{"content": "a"}],
            "key_values": [{"key": "k", "value": "v"}],
        },
        "tables": [{"table_id": "pt_1_0", "headers": []}],
        "regions": [
            {
                "region_id": "rg_x",
                "structure": {"cells": []},
            }
        ],
    }
    assert resolve_block_ref(api_page, "text:0") == {"content": "a"}
    assert resolve_block_ref(api_page, "kv:0") == {"key": "k", "value": "v"}
    assert resolve_block_ref(api_page, "table:pt_1_0")["table_id"] == "pt_1_0"
    assert resolve_block_ref(api_page, "region:rg_x")["region_id"] == "rg_x"


def test_morphology_summary_from_blocks():
    blocks = [
        PageBlock(block_id="a", morphology="S1", kind="text_flow", ref="text:0"),
        PageBlock(block_id="b", morphology="S2", kind="physical_table", ref="table:t"),
    ]
    assert morphology_summary_from_blocks(blocks) == {"S1": 1, "S2": 1}


def test_pcm_blocks_enabled_default_on():
    assert pcm_blocks_enabled() is True
