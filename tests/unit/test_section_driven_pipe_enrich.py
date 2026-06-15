# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Phase 3: section-led documents with embedded pipe grid enrich + SPE."""

from __future__ import annotations

from dataclasses import dataclass, field

from docmirror.core.analyze.structure_provenance import apply_pipe_enrich_spe
from docmirror.core.extraction.extractor import CoreExtractor
from docmirror.core.extraction.strategies.section_driven import (
    SectionDrivenStrategy,
    _enrich_pages_with_pipe_tables,
)
from tests.unit.test_pipe_text_table_builder import BOC_HEADER, BOC_ROW1, _synthetic_boc_text


def _credit_report_page() -> str:
    return "\n".join([
        "个人信用报告",
        "一  个人基本信息",
        "姓名：张三",
        "二  信息概要",
        "三  信贷交易信息明细",
        "（一）非循环贷账户",
        "四  查询记录",
        "五  异议标注",
        "六  说明",
    ])


def _pipe_attachment_rows(n: int = 20) -> str:
    rows = []
    for i in range(2, n + 2):
        rows.append(
            f"| {i:2d} |220401|220401|网上支付|    |ref{i}|        100.00|                  |"
            f"           {1000 + i}.00|ref |counterparty |"
        )
    return _synthetic_boc_text(rows)


class _MockPage:
    def __init__(self, text: str) -> None:
        self._text = text

    def get_text(self) -> str:
        return self._text


class _MockFitzDoc:
    def __init__(self, pages: list[str]) -> None:
        self._pages = [_MockPage(t) for t in pages]

    def __len__(self) -> int:
        return len(self._pages)

    def __getitem__(self, idx: int) -> _MockPage:
        return self._pages[idx]


@dataclass
class _FakePreAnalysis:
    content_type: str = "section_dominant"
    structure_spe: dict = field(default_factory=dict)


def test_enrich_adds_table_block_to_pages():
    from docmirror.models.entities.domain import PageLayout

    section_text = _credit_report_page()
    pipe_text = _pipe_attachment_rows(20)
    full_text = section_text + "\n\n" + pipe_text

    pages = [PageLayout(page_number=1, blocks=())]
    enriched, did = _enrich_pages_with_pipe_tables(pages, full_text)
    assert did is True
    table_blocks = [b for b in enriched[0].blocks if b.block_type == "table"]
    assert len(table_blocks) == 1
    assert len(table_blocks[0].raw_content) >= 3


def test_section_strategy_enrich_on_mixed_mock_doc():
    """SSO sample pages lack pipe; full doc has embedded ledger (征信附流水)."""
    doc = _MockFitzDoc([_credit_report_page(), _pipe_attachment_rows(20)])
    pre = _FakePreAnalysis(
        structure_spe={
            "primary": "section_led",
            "competitors": {"H_section": 0.72, "H_pipe_grid": 0.1},
            "table_extraction": "skipped",
            "table_extraction_skipped_reason": "route_section_dominant",
            "sso_version": "1.0",
        }
    )

    pages, full_text, layer, conf, perf, _ = SectionDrivenStrategy().extract(doc, pre)
    assert layer == "section_driven"
    assert perf.get("pipe_table_enrich") is True
    table_count = sum(1 for p in pages for b in p.blocks if b.block_type == "table")
    assert table_count >= 1
    assert BOC_HEADER.split("|")[1] in full_text or "序号" in full_text


def test_build_structure_metadata_enrich_only_spe():
    doc = _MockFitzDoc([_credit_report_page(), _pipe_attachment_rows(20)])
    pre = _FakePreAnalysis(
        structure_spe={
            "primary": "section_led",
            "competitors": {"H_section": 0.72, "H_pipe_grid": 0.1},
            "table_extraction": "skipped",
            "table_extraction_skipped_reason": "route_section_dominant",
            "sso_version": "1.0",
        }
    )
    spe = CoreExtractor._build_structure_metadata(
        pre_analysis=pre,
        fitz_doc=doc,
        table_count=1,
        extraction_layer="section_driven",
        layout_profile_id=None,
        pipe_table_enrich=True,
    )
    assert spe["table_extraction"] == "enrich_only"
    assert spe["table_extraction_skipped_reason"] is None
    assert spe["primary"] == "section_led"
    assert spe["extraction_layer"] == "section_driven"


def test_apply_pipe_enrich_spe_helper():
    base = {
        "primary": "section_led",
        "table_extraction": "skipped",
        "table_extraction_skipped_reason": "route_section_dominant",
    }
    out = apply_pipe_enrich_spe(base)
    assert out["table_extraction"] == "enrich_only"
    assert out["table_extraction_skipped_reason"] is None
