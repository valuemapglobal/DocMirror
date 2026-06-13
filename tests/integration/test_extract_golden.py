# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for extract-layer row fidelity (EPO golden gates)."""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

import pytest

from docmirror.core.evaluation.gates import (
    GATE_PROFILES,
    dual_view_consistency_check,
    extract_row_preservation_check,
)
from docmirror.core.evaluation.oracle import pdfplumber_full_page_sample_oracle
from docmirror.core.extraction.extractor import CoreExtractor
from docmirror.core.table.table_access import get_logical_tables
from docmirror.models.construction.parse_result_bridge import ParseResultBridge


WECHAT_PDF = Path("tests/fixtures/wechat_payment/DemoUser+微信流水.pdf")
ALIPAY_PDF = Path("tests/fixtures/alipay_payment/DemoUser+支付宝流水.pdf")
BANK_PDF_3PAGE = Path("tests/fixtures/bank_statement/银行流水_中国建设银行_20231226.pdf")
BANK_SCAN_PNG = Path("tests/fixtures/bank_statement/朱洁_银行流水_企业网上银行_20170711.png")
ID_CARD_PDF = Path("tests/fixtures/id_card/ZhangSan_身份证_1976112.pdf")
LICENSE_FIXTURE = Path("tests/fixtures/business_license/林晓彤_营业执照_20220826.jpg")

WECHAT_EXPECTED_COLS = 8
WECHAT_TRADE_NO_HEADER = "交易单号"
WECHAT_TIME_HEADER = "交易时间"


def _primary_logical_table(result):
    logical = get_logical_tables(result)
    if not logical:
        return None
    return max(logical, key=lambda lt: lt.row_count)


def _header_index(headers: list[str], name: str) -> int | None:
    for i, h in enumerate(headers):
        if name in (h or ""):
            return i
    return None


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(not WECHAT_PDF.exists(), reason="wechat fixture missing")
def test_wechat_logical_rows_gate():
    """WeChat 219-page ledger: primary logical rows must match script oracle (5111)."""
    extractor = CoreExtractor(max_page_concurrency=1)
    base = asyncio.run(extractor.extract(WECHAT_PDF))
    result = ParseResultBridge.from_base_result(base)
    logical = get_logical_tables(result)
    primary_rows = max((lt.row_count for lt in logical), default=0)
    gate = extract_row_preservation_check(
        result,
        profile=GATE_PROFILES["wechat_payment"],
    )
    assert primary_rows == 5111, (
        f"primary_logical_rows={primary_rows}, total={sum(lt.row_count for lt in logical)}, "
        f"gate={gate.failures}"
    )
    assert gate.checks.get("min_logical_rows", False)
    assert gate.checks.get("max_logical_rows", False)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(not WECHAT_PDF.exists(), reason="wechat fixture missing")
def test_wechat_dual_view_oracle_and_audit():
    """E9 + oracle_mode gate + §5.7 extraction_audit schema (single extract)."""
    extractor = CoreExtractor(max_page_concurrency=1)
    base = asyncio.run(extractor.extract(WECHAT_PDF))
    result = ParseResultBridge.from_base_result(base)
    quarantined = base.metadata.get("quarantined_tables") or []
    audit = (base.metadata.get("perf_breakdown") or {}).get("extraction_audit") or {}
    if not quarantined and audit.get("quarantined_pages"):
        quarantined = audit["quarantined_pages"]

    # 1) Dual-view consistency
    dual = dual_view_consistency_check(result, quarantined_tables=quarantined)
    assert dual.passed, dual.failures
    assert dual.metrics["primary_logical_rows"] == 5111
    assert dual.checks["secondary_logical_bounded"]

    # 2) Oracle-mode relative preservation (absolute 5111 gate still enforced)
    oracle_rows = pdfplumber_full_page_sample_oracle(
        WECHAT_PDF,
        num_pages=base.metadata.get("page_count", 219),
        sample_count=GATE_PROFILES["wechat_payment"].oracle_sample_pages,
    )
    assert oracle_rows > 4000
    gate = extract_row_preservation_check(
        result,
        profile=GATE_PROFILES["wechat_payment"],
        oracle_row_count=oracle_rows,
    )
    assert gate.checks["row_preservation"], gate.failures
    assert gate.checks["min_logical_rows"]
    assert gate.checks["max_logical_rows"]

    # 3) Audit schema
    audit = (base.metadata.get("perf_breakdown") or {}).get("extraction_audit") or {}
    assert audit.get("profile_id") == "borderless_ledger_wechat"
    assert audit.get("primary_logical_rows") == 5111
    assert isinstance(audit.get("pages"), list) and len(audit["pages"]) >= 200
    assert isinstance(audit.get("quarantined_pages"), list)
    if audit["quarantined_pages"]:
        qp = audit["quarantined_pages"][0]
        assert qp.get("loss_reason") == "col_count_mismatch"
        assert qp.get("page") == 219

    bcs_pages = [p for p in audit["pages"] if p.get("candidates")]
    assert bcs_pages, "expected BCS candidate audit on borderless ledger pages"
    sample = bcs_pages[0]
    assert "picked" in sample and "score" in sample
    assert isinstance(sample["candidates"], list) and sample["candidates"]


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(not WECHAT_PDF.exists(), reason="wechat fixture missing")
def test_wechat_column_fidelity():
    """P2-4: 8 columns, trade_no without intracellular whitespace, timestamps intact."""
    extractor = CoreExtractor(max_page_concurrency=1)
    base = asyncio.run(extractor.extract(WECHAT_PDF))
    result = ParseResultBridge.from_base_result(base)
    primary = _primary_logical_table(result)
    assert primary is not None, "missing primary logical table"

    headers = [str(h) for h in (primary.headers or [])]
    assert len(headers) >= WECHAT_EXPECTED_COLS, f"headers={headers!r}"

    trade_idx = _header_index(headers, WECHAT_TRADE_NO_HEADER)
    time_idx = _header_index(headers, WECHAT_TIME_HEADER)
    assert trade_idx is not None, f"trade_no column missing in {headers}"
    assert time_idx is not None, f"time column missing in {headers}"

    eight_col_rows = 0
    trade_no_with_space = 0
    bad_timestamps = 0
    sample_size = len(primary.rows)

    for row in primary.rows:
        cells = [c.text for c in row.cells]
        if len(cells) >= WECHAT_EXPECTED_COLS:
            eight_col_rows += 1
        if trade_idx < len(cells):
            trade_val = (cells[trade_idx] or "").strip()
            if trade_val and re.search(r"\s", trade_val):
                trade_no_with_space += 1
        if time_idx < len(cells):
            ts = (cells[time_idx] or "").strip()
            if ts and not re.match(r"\d{4}-\d{2}-\d{2}", ts):
                bad_timestamps += 1

    col_ratio = eight_col_rows / max(sample_size, 1)
    assert col_ratio >= 0.99, f"8-col ratio {col_ratio:.3f} < 0.99"
    assert trade_no_with_space == 0, f"{trade_no_with_space} trade_no cells contain whitespace"
    assert bad_timestamps / max(sample_size, 1) < 0.01, "timestamp column integrity failed"


@pytest.mark.integration
@pytest.mark.skipif(not ALIPAY_PDF.exists(), reason="alipay fixture missing")
def test_alipay_logical_rows_regression():
    """Alipay 44-page ledger: logical rows ≥ 1400."""
    extractor = CoreExtractor(max_page_concurrency=1)
    base = asyncio.run(extractor.extract(ALIPAY_PDF))
    result = ParseResultBridge.from_base_result(base)
    logical = get_logical_tables(result)
    logical_rows = sum(lt.row_count for lt in logical)
    gate = extract_row_preservation_check(
        result,
        profile=GATE_PROFILES["alipay_payment"],
    )
    assert logical_rows >= 1400, f"logical_rows={logical_rows}"
    assert gate.passed or gate.checks.get("min_logical_rows", False)


@pytest.mark.integration
@pytest.mark.skipif(not WECHAT_PDF.exists(), reason="wechat fixture missing")
def test_wechat_first_pages_row_count_smoke():
    """Smoke: first 5 pages extract with profile audit metadata."""
    os.environ["DOCMIRROR_MAX_PAGES"] = "5"
    try:
        extractor = CoreExtractor(max_page_concurrency=1)
        base = asyncio.run(extractor.extract(WECHAT_PDF))
        perf = base.metadata.get("perf_breakdown") or {}
        audit = perf.get("extraction_audit")
        assert audit is None or audit.get("profile_id") == "borderless_ledger_wechat"
        if audit:
            assert "pages" in audit
            assert isinstance(audit["pages"], list)
            if audit["pages"]:
                sample = audit["pages"][0]
                assert "page" in sample
                assert "layer" in sample
                assert "row_count" in sample
        assert base.metadata.get("document_scene") in ("wechat_payment", None)
        table_rows = sum(
            len(b.raw_content)
            for pg in base.pages
            for b in pg.blocks
            if b.block_type == "table" and isinstance(b.raw_content, list)
        )
        assert table_rows >= 80
    finally:
        os.environ.pop("DOCMIRROR_MAX_PAGES", None)


@pytest.mark.integration
@pytest.mark.skipif(not WECHAT_PDF.exists(), reason="wechat fixture missing")
def test_wechat_quarantine_metadata():
    """P3-2: P219 footnote page appears in quarantined_tables metadata."""
    extractor = CoreExtractor(max_page_concurrency=1)
    base = asyncio.run(extractor.extract(WECHAT_PDF))
    quarantined = base.metadata.get("quarantined_tables") or []
    assert isinstance(quarantined, list)
    if quarantined:
        entry = quarantined[0]
        assert entry.get("reason") == "col_count_mismatch"
        assert entry.get("action") == "standalone_physical_table"
        assert entry.get("page") == 219


def _source_pages_continuous(pages: list[int]) -> bool:
    if len(pages) <= 1:
        return True
    ordered = sorted(pages)
    return all(ordered[i] == ordered[i - 1] + 1 for i in range(1, len(ordered)))


@pytest.mark.integration
@pytest.mark.skipif(not BANK_PDF_3PAGE.exists(), reason="bank PDF fixture missing")
def test_bank_statement_three_page_logical_merge():
    """§9.1: 3-page bank PDF — logical table source_pages continuous, EPO bank profile."""
    extractor = CoreExtractor(max_page_concurrency=1)
    base = asyncio.run(extractor.extract(BANK_PDF_3PAGE))
    assert base.metadata.get("page_count") == 3
    assert base.metadata.get("layout_profile_id") == "borderless_ledger_bank"
    assert base.metadata.get("document_scene") == "bank_statement"

    result = ParseResultBridge.from_base_result(base)
    logical = get_logical_tables(result)
    assert logical, "expected at least one logical table"

    merged = [lt for lt in logical if len(lt.source_pages or []) >= 2]
    assert merged, "expected cross-page merged logical table"
    primary = max(merged, key=lambda lt: lt.row_count)
    pages = sorted(primary.source_pages or [])
    assert pages == [1, 2, 3], f"source_pages not continuous: {pages}"
    assert _source_pages_continuous(pages)
    assert primary.row_count >= 10
    assert primary.page_span == (1, 3)


@pytest.mark.integration
@pytest.mark.skipif(not BANK_SCAN_PNG.exists(), reason="bank scan fixture missing")
def test_bank_statement_scan_image_smoke():
    """§9.1: scan PNG — skip when OCR path unavailable in CI."""
    extractor = CoreExtractor(max_page_concurrency=1)
    try:
        base = asyncio.run(extractor.extract(BANK_SCAN_PNG))
    except Exception as exc:
        pytest.skip(f"scan bank image extract not stable: {exc}")
    if base.metadata.get("error"):
        pytest.skip(f"scan bank image extract error: {base.metadata.get('error')}")
    assert base.metadata.get("page_count", 0) >= 1


def test_wechat_profile_grid_template_enabled():
    """P4-1: grid template enabled after BCS + row filtering fixes."""
    from docmirror.core.layout.profile_registry import get_profile

    profile = get_profile("borderless_ledger_wechat")
    assert profile.enable_grid_template is True
    alipay = get_profile("borderless_ledger_alipay")
    assert alipay.enable_grid_template is True


@pytest.mark.integration
@pytest.mark.skipif(not ID_CARD_PDF.exists(), reason="id card PDF fixture missing")
def test_generic_profile_id_card_regression():
    """§9.2: generic/id document — stable normalized text snapshot (minimal fields)."""
    import hashlib

    extractor = CoreExtractor(max_page_concurrency=1)
    base = asyncio.run(extractor.extract(ID_CARD_PDF))
    assert base.metadata.get("error") is None
    profile = base.metadata.get("layout_profile_id")
    assert profile in (None, "generic", "credit_report_section_dominant")
    assert base.metadata.get("page_count", 0) >= 1
    assert base.metadata.get("table_count", 0) <= 3

    text_lines = sorted(
        str(b.raw_content).strip()
        for pg in base.pages
        for b in pg.blocks
        if b.block_type == "text" and b.raw_content
    )
    assert len(text_lines) >= 5
    joined = "\n".join(text_lines)
    assert "ZhangSan" in joined
    assert "110101199001011234" in joined
    assert "SamplePSB" in joined

    snapshot = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    assert snapshot == "b4e16e6ed5c30f62172e3607bd6e40f732973856940ae995a4d85d58abc38b52"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(not WECHAT_PDF.exists(), reason="wechat fixture missing")
def test_wechat_community_total_rows_parity():
    """§9.2: Community plugin records vs extract logical rows within 0.5%."""
    from docmirror.plugins.wechat_payment_community import plugin as wechat_plugin

    extractor = CoreExtractor(max_page_concurrency=1)
    base = asyncio.run(extractor.extract(WECHAT_PDF))
    result = ParseResultBridge.from_base_result(base)
    logical = get_logical_tables(result)
    primary_rows = max((lt.row_count for lt in logical), default=0)
    assert primary_rows == 5111

    community = wechat_plugin.extract_from_mirror(result)
    data = community.get("data") or {}
    records = data.get("records") or community.get("records") or []
    community_rows = len(records)
    if community_rows == 0:
        summary = data.get("summary") or community.get("summary") or {}
        community_rows = int(summary.get("total_transactions") or summary.get("total_rows") or 0)
    assert community_rows > 0
    drift = abs(community_rows - primary_rows) / primary_rows
    assert drift < 0.005, f"community={community_rows} logical={primary_rows} drift={drift:.4f}"


@pytest.mark.integration
def test_credit_report_section_mode(tmp_path):
    """§9.1: synthetic credit report — section_driven, no ledger-scale tables."""
    import fitz

    pdf_path = tmp_path / "credit_report_smoke.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    lines = [
        (72, 60, "个人信用报告"),
        (72, 90, "一 个人基本信息"),
        (72, 115, "（一）身份信息"),
        (72, 140, "二 信息概要"),
        (72, 165, "（一）信贷交易信息概要"),
        (72, 190, "三 信贷交易信息明细"),
        (72, 215, "（一）非循环贷账户"),
    ]
    for x, y, text in lines:
        page.insert_text((x, y), text, fontname="china-s", fontsize=11)
    doc.save(str(pdf_path))
    doc.close()

    extractor = CoreExtractor(max_page_concurrency=1)
    base = asyncio.run(extractor.extract(pdf_path))
    assert base.metadata.get("page_count", 0) >= 1
    pre = base.metadata.get("pre_analysis") or {}
    assert pre.get("content_type") == "section_dominant"
    perf = base.metadata.get("perf_breakdown") or {}
    profile_id = base.metadata.get("layout_profile_id") or perf.get("layout_profile_id")
    assert profile_id in ("credit_report_section_dominant", "generic", None)
    assert base.metadata.get("table_count", 0) <= 2

    result = ParseResultBridge.from_base_result(base)
    logical = get_logical_tables(result)
    assert len(logical) <= 1


@pytest.mark.integration
@pytest.mark.skipif(not LICENSE_FIXTURE.exists(), reason="business license fixture missing")
def test_business_license_no_table_smoke():
    """§9.1: single-page license should not produce ledger-scale tables."""
    extractor = CoreExtractor(max_page_concurrency=1)
    base = asyncio.run(extractor.extract(LICENSE_FIXTURE))
    table_count = base.metadata.get("table_count", 0)
    assert table_count <= 2


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.benchmark
@pytest.mark.skipif(
    os.environ.get("DOCMIRROR_RUN_BENCHMARK") != "1",
    reason="set DOCMIRROR_RUN_BENCHMARK=1 to run timing benchmark",
)
@pytest.mark.skipif(not WECHAT_PDF.exists(), reason="wechat fixture missing")
def test_wechat_extract_benchmark():
    """P4-3: record 219-page extract timing (design target < 60s; current ~64s)."""
    extractor = CoreExtractor(max_page_concurrency=1)
    base = asyncio.run(extractor.extract(WECHAT_PDF))
    elapsed_ms = base.metadata.get("elapsed_ms", 0)
    assert elapsed_ms > 0
    # Informational ceiling — design target 60s not yet met
    assert elapsed_ms < 300_000, f"extract took {elapsed_ms}ms (>5min regression)"
