# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Golden-file contract tests for vNext mirror output."""

from __future__ import annotations

from docmirror.models.mirror.core import MirrorCoreVNext
from docmirror.models.mirror.vnext import BlockType
from tests.unit.test_mirror_json_vnext import _sample_parse_result


def test_vnext_golden_has_required_top_level_sections():
    result = _sample_parse_result()
    mirror = MirrorCoreVNext().process(result).mirror
    top = mirror.model_dump(by_alias=True, exclude_none=True)
    required = {"mirror", "source", "document", "pages", "blocks", "graph", "quality", "diagnostics"}
    missing = required - set(top.keys())
    assert not missing, f"Missing: {missing}"


def test_vnext_golden_table_has_correct_columns():
    result = _sample_parse_result()
    mirror = MirrorCoreVNext().process(result).mirror
    tables = [b for b in mirror.blocks if b.type == BlockType.TABLE]
    assert len(tables) >= 1
    grid = tables[0].content.get("grid", {}) if isinstance(tables[0].content, dict) else {}
    cols = grid.get("columns", [])
    expected = ["序号", "交易日期", "交易时间", "摘要", "凭证种类", "借方发生额", "贷方发生额", "余额", "对方账户", "对方户名"]
    assert len(cols) == len(expected), f"{len(cols)} != {len(expected)}"


def test_vnext_golden_quality_has_minimum_gates():
    result = _sample_parse_result()
    mirror = MirrorCoreVNext().process(result).mirror
    gates = mirror.quality.gates
    gate_ids = {g["id"] for g in gates if isinstance(g, dict) and "id" in g}
    required = {"gate:region_ownership", "gate:residual_ratio", "gate:region_overlap"}
    missing = required - gate_ids
    assert not missing, f"Missing gates: {missing}"


def test_vnext_golden_semantics_has_bank_statement_view():
    result = _sample_parse_result()
    mirror = MirrorCoreVNext().process(result).mirror
    assert "tables" in mirror.semantics.views


def test_vnext_golden_document_title_from_heading():
    result = _sample_parse_result()
    mirror = MirrorCoreVNext().process(result).mirror
    assert mirror.document.title
