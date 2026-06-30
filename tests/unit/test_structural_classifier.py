# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SSO structural classifier unit tests (Phase 1 / ADR-M13-01)."""

from __future__ import annotations

from docmirror.layout.structural_classifier import (
    classify_structure,
    content_type_from_verdict,
)
from docmirror.layout.structure_signals import apply_scene_hint_prior
from tests.unit.test_pipe_text_table_builder import _synthetic_boc_text


def _synthetic_boc_with_rows(row_count: int = 20) -> str:
    rows = []
    for i in range(2, row_count + 2):
        rows.append(
            f"| {i:2d} |220401|220401|网上支付|    |ref{i}|        100.00|                  |"
            f"           {1000 + i}.00|ref |counterparty |"
        )
    return _synthetic_boc_text(rows)


def _credit_report_sample() -> str:
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


def test_boc_pipe_veto_promotes_table_led():
    section_block = "\n".join([f"一  章节标题{i}" for i in range(4)])
    text = section_block + "\n" + _synthetic_boc_with_rows(20)
    verdict = classify_structure(
        sample_text=text,
        scene_hint="bank_statement",
        table_pages=0,
        sample_size=3,
        has_text=True,
    )
    assert verdict.primary == "table_led"
    assert verdict.scores["H_pipe_grid"] >= 0.85
    assert "H_pipe_grid_veto_section_monopoly" in verdict.veto_applied
    assert verdict.spe.table_extraction_skipped_reason is None
    assert content_type_from_verdict(verdict) == "table_dominant"


def test_credit_report_stays_section_led():
    verdict = classify_structure(
        sample_text=_credit_report_sample(),
        scene_hint="credit_report",
        table_pages=0,
        sample_size=3,
        has_text=True,
    )
    assert verdict.primary == "section_led"
    assert verdict.scores["H_pipe_grid"] < 0.5
    assert content_type_from_verdict(verdict) == "section_dominant"
    assert verdict.spe.table_extraction == "skipped"
    assert verdict.spe.table_extraction_skipped_reason == "route_section_dominant"


def test_scene_hint_weak_prior_bounded():
    from docmirror.configs.structure_policy import scene_hint_prior_delta

    delta = scene_hint_prior_delta()
    base = {"H_pipe_grid": 0.5, "H_section": 0.5, "H_table_pdf": 0.0}
    boosted = apply_scene_hint_prior(dict(base), "bank_statement")
    assert boosted["H_pipe_grid"] <= base["H_pipe_grid"] + delta + 1e-9
    credit = apply_scene_hint_prior(dict(base), "credit_report")
    assert credit["H_section"] <= base["H_section"] + delta + 1e-9


def test_markdown_not_mismatch_reason():
    md = "\n".join([
        "| Name | Age |",
        "| --- | --- |",
        "| A | 1 |",
    ])
    verdict = classify_structure(sample_text=md, has_text=True)
    assert verdict.scores["H_pipe_grid"] < 0.85
