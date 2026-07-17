# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
TQG unified runner — executes manifest cases and produces gate reports.

Orchestrates end-to-end TQG evaluation: resolves fixture paths, runs
``perceive_document`` (or targeted oracle hooks), evaluates gate specs via
``gates_eval``, and aggregates ``GateReport`` results with failure-class
attribution. Supports async batch execution and licensing-track mocks.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from docmirror.eval.gates import (
    GATE_PROFILES,
    FailureClass,
    dual_view_consistency_check,
    extract_row_preservation_check,
)
from docmirror.eval.oracle import pdfplumber_full_page_sample_oracle
from docmirror.eval.tqg.gates_eval import eval_gate, resolve_dot_path
from docmirror.eval.tqg.manifest import TQGCase
from docmirror.eval.tqg.report import GateReport
from docmirror.evidence.spe_consumer import mirror_expected_primary_rows
from docmirror.input.bridge.parse_result_bridge import ParseResultBridge
from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.input.extraction.extractor import CoreExtractor
from docmirror.plugins._runtime.community import community_plugin_import_path
from docmirror.tables.access import get_logical_tables

logger = logging.getLogger(__name__)

_PLUGIN_MODULES: dict[str, str] = {
    "wechat_payment": community_plugin_import_path("wechat_payment"),
    "alipay_payment": community_plugin_import_path("alipay_payment"),
    "bank_statement": community_plugin_import_path("bank_statement"),
}


def _failure_class_from_str(name: str | None) -> FailureClass | None:
    if not name:
        return None
    try:
        return FailureClass(name)
    except ValueError:
        return FailureClass.UNKNOWN


def _local_structure_bundle_domain(
    *,
    page: int,
    page_width: int | float,
    page_height: int | float,
    lines: list[dict[str, Any]],
    evidence: dict[str, Any],
    **extra: Any,
) -> dict[str, Any]:
    from docmirror.models.mirror.page_evidence_bundles import (
        domain_specific_with_page_bundles,
        page_evidence_bundle,
    )

    return domain_specific_with_page_bundles(
        page_evidence_bundle(
            page,
            page_width=page_width,
            page_height=page_height,
            local_structure_evidence={
                "page": page,
                "page_width": page_width,
                "page_height": page_height,
                "lines": lines,
                "candidates": evidence.get("candidates") or [],
                "structures": evidence.get("structures") or [],
            },
        ),
        **extra,
    )


async def _execute_extract_only(case: TQGCase) -> tuple[Any, dict[str, Any]]:
    opts = case.options
    if opts.get("max_pages"):
        os.environ["DOCMIRROR_MAX_PAGES"] = str(opts["max_pages"])
    try:
        concurrency = int(opts.get("max_page_concurrency", 1))
        extractor = CoreExtractor(max_page_concurrency=concurrency)
        base = await extractor.extract(case.fixture)
        result = ParseResultBridge.from_base_result(base)
        quarantined = base.metadata.get("quarantined_tables") or []
        audit = (base.metadata.get("perf_breakdown") or {}).get("extraction_audit") or {}
        if not quarantined and audit.get("quarantined_pages"):
            quarantined = audit["quarantined_pages"]
        meta: dict[str, Any] = {
            "base": base,
            "quarantined": quarantined,
            "page_count": base.metadata.get("page_count", 0),
            "table_count": base.metadata.get("table_count", 0),
            "document_scene": base.metadata.get("document_scene"),
            "structure": base.metadata.get("structure"),
            "ltqg": base.metadata.get("ltqg"),
        }
        return result, meta
    finally:
        if opts.get("max_pages"):
            os.environ.pop("DOCMIRROR_MAX_PAGES", None)


async def _execute_classify_text(case: TQGCase) -> tuple[Any, dict[str, Any]]:
    """Run EvidenceEngine on a keyword-rich text fixture (no full extraction)."""
    from docmirror.layout.scene.evidence_engine import EvidenceEngine
    from docmirror.models.entities.parse_result import PageContent, ParseResult, TextBlock, TextLevel

    text = case.fixture.read_text(encoding="utf-8")
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                texts=[TextBlock(content=text, level=TextLevel.TITLE)],
            )
        ]
    )
    result = EvidenceEngine().process(result)
    return result, {"page_count": 1, "table_count": 0}


async def _execute_perceive(case: TQGCase) -> tuple[Any, dict[str, Any]]:
    opts = case.options
    perceive_opts = PerceiveOptions(
        enhance_mode=str(opts.get("enhance_mode", "standard")),
        max_pages=opts.get("max_pages"),
    )
    parse_result = await perceive_document(case.fixture, perceive_opts)
    api = parse_result.to_mirror_json_vnext() if hasattr(parse_result, "to_mirror_json_vnext") else {}
    pages = api.get("pages") if isinstance(api, dict) else None
    blocks = api.get("blocks") if isinstance(api, dict) else None
    meta: dict[str, Any] = {
        "parse_result": parse_result,
        "page_count": getattr(parse_result, "page_count", None) or len(pages or []),
        "table_count": getattr(parse_result, "total_tables", None)
        or sum(1 for block in (blocks or []) if isinstance(block, dict) and block.get("type") == "table"),
    }
    return parse_result, meta


def _edition_from_plugin(mirror: Any, document_type: str) -> dict[str, Any] | None:
    module_path = _PLUGIN_MODULES.get(document_type)
    if not module_path:
        return None
    try:
        mod = importlib.import_module(module_path)
        plugin = getattr(mod, "plugin", None)
        if plugin is None:
            return None
        return plugin.extract_from_mirror(mirror)
    except ImportError:
        logger.debug("edition plugin not available: %s", module_path)
        return None


def _edition_package_available(edition: str) -> bool:
    modules = {"enterprise": "docmirror_enterprise", "finance": "docmirror_finance"}
    module_path = modules.get(edition)
    if not module_path:
        return True
    try:
        importlib.import_module(module_path)
        return True
    except ImportError:
        return False


async def _execute_edition(case: TQGCase) -> tuple[dict[str, Any], dict[str, Any]]:
    mirror, meta = await _execute_perceive(case)
    edition_name = case.editions[0] if case.editions else "community"
    if case.optional_edition and edition_name in ("enterprise", "finance"):
        if not _edition_package_available(edition_name):
            meta["edition_skipped"] = edition_name
            return {"mirror": mirror, "edition": None}, meta
    edition_payload: dict[str, Any] | None = None
    if edition_name == "community":
        from docmirror.plugins._runtime.runner import _plugin_document_type, _run_community_extract

        doc_type = getattr(getattr(mirror, "entities", None), "document_type", "") or ""
        edition_payload = _run_community_extract(
            mirror,
            _plugin_document_type(mirror, doc_type),
            getattr(mirror, "full_text", "") or "",
        )
        if edition_payload is None:
            from docmirror.plugins._runtime.runner import run_plugin_extract_sync

            edition_payload = run_plugin_extract_sync(
                mirror,
                edition="community",
                full_text=getattr(mirror, "full_text", "") or "",
                file_path=str(getattr(mirror, "file_path", "") or case.fixture),
            )
    else:
        doc_type = getattr(getattr(mirror, "entities", None), "document_type", "") or ""
        edition_payload = _edition_from_plugin(mirror, doc_type)
    meta["edition_payload"] = edition_payload
    meta["edition_name"] = edition_name
    return {"mirror": mirror, "edition": edition_payload}, meta


async def _execute_transport_capability(case: TQGCase) -> tuple[Any, dict[str, Any]]:
    from docmirror.configs.format.resolver import resolve_capability

    hint = str(case.options.get("path_hint", "file.pdf"))
    cap = resolve_capability(Path(hint))
    binding = cap.binding
    meta: dict[str, Any] = {
        "capability_id": cap.id,
        "capability_status": cap.status,
        "capability_transport": cap.transport,
        "content_model": cap.content_model,
        "capability_binding_present": binding is not None,
        "binding_deserializer": getattr(binding, "deserializer", None) if binding else None,
    }
    return cap, meta


async def _execute_transport_dispatch(case: TQGCase) -> tuple[Any, dict[str, Any]]:
    from docmirror.framework.dispatcher import ParserDispatcher

    hint = str(case.options.get("path_hint", "file.bin"))
    raw = case.options.get("bytes_hex", "00")
    if isinstance(raw, str):
        data = bytes.fromhex(raw)
    else:
        data = bytes(raw)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / hint
        path.write_bytes(data)
        dispatcher = ParserDispatcher()
        if case.options.get("mock_soffice_missing"):
            with patch("shutil.which", return_value=None):
                result = await dispatcher.process(path)
        else:
            result = await dispatcher.process(path)
    error_code = result.error.code if result.error else None
    meta: dict[str, Any] = {
        "dispatch_status": result.status.value,
        "error_code": error_code,
    }
    return result, meta


async def _execute_e2e_four_file(case: TQGCase) -> tuple[dict[str, Any], dict[str, Any]]:
    from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
    from docmirror.server.edition_outputs import write_four_files

    mode = str(case.options.get("mode", "synthetic"))
    meta: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)
        if mode == "perceive":
            mirror, perceive_meta = await _execute_perceive(case)
            meta.update(perceive_meta)
            task_id, written = write_four_files(
                mirror,
                out_dir,
                file_path=str(case.fixture) if case.fixture else "",
                full_text=getattr(mirror, "full_text", "") or "",
            )
        else:
            doc_type = str(case.options.get("document_type", "business_license"))
            mirror = ParseResult(status=ResultStatus.SUCCESS)
            mirror.entities = DocumentEntities(document_type=doc_type)
            task_id, written = write_four_files(
                mirror,
                out_dir,
                file_id="001",
                task_id="test_task_001",
            )
        mirror_path = written.get("mirror")
        community_path = written.get("community")
        mirror_has_no_editions = True
        if mirror_path and mirror_path.is_file():
            mirror_data = json.loads(mirror_path.read_text(encoding="utf-8"))
            mirror_has_no_editions = "editions" not in mirror_data.get("data", {})
        checks = {
            "mirror_file_written": bool(mirror_path and mirror_path.is_file()),
            "community_file_written": bool(community_path and community_path.is_file()),
            "mirror_has_no_editions_key": mirror_has_no_editions,
            "task_id": task_id,
        }
        meta.update(checks)
        return checks, meta


async def _execute_e2e_contract(case: TQGCase) -> tuple[dict[str, Any], dict[str, Any]]:
    from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
    from docmirror.server.edition_outputs import build_all_projections

    contract = str(case.options.get("contract", ""))
    passed = False
    if contract == "parse_result_projection_boundary":
        result = ParseResult(status=ResultStatus.SUCCESS)
        result.entities = DocumentEntities(document_type="business_license")
        outputs = build_all_projections(result, editions=("community",))
        passed = (
            outputs.get("mirror") is not None
            and (outputs.get("community") or {}).get("edition") == "community"
            and not hasattr(result, "editions")
            and "_edition_outputs" not in (result.entities.domain_specific or {})
        )
    elif contract == "enterprise_not_generated":
        mirror = ParseResult(status=ResultStatus.SUCCESS)
        mirror.entities = DocumentEntities(document_type="business_license")
        try:
            importlib.import_module("docmirror_enterprise")
        except ImportError:
            outputs = build_all_projections(mirror)
            passed = outputs.get("enterprise") is None
        else:
            passed = True
    return {"contract_passed": passed}, {"contract_passed": passed}


async def _execute_mirror_conservation_contract(case: TQGCase) -> tuple[Any, dict[str, Any]]:
    scenario = str(case.options.get("scenario", "passing_table"))
    payload = {
        "data": {
            "document": {
                "text": "Synthetic conservation text",
                "raw_text": "Synthetic conservation text",
                "pages": [
                    {
                        "page_number": 1,
                        "width": 612,
                        "height": 792,
                        "flow": {"texts": [{"content": "Synthetic conservation text", "evidence_ids": ["txt_1"]}]},
                        "texts": [{"content": "Synthetic conservation text", "evidence_ids": ["txt_1"]}],
                        "tables": [
                            {
                                "table_id": "pt_1_0",
                                "extraction_layer": "synthetic",
                                "evidence_ids": ["tbl_1"],
                                "rows": [{"cells": [{"text": "1"}]}],
                            }
                        ],
                    }
                ],
                "logical_tables": [{"logical_id": "lt_1", "row_count": 1, "rows": [{"cells": [{"text": "1"}]}]}],
            }
        },
        "meta": {
            "conservation": {
                "passed": True,
                "error_count": 0,
                "warning_count": 0,
                "issues": [],
                "metrics": {
                    "physical_table_count": 1,
                    "logical_table_count": 1,
                    "logical_row_count": 1,
                    "evidence_span_count": 2,
                    "hypothesis_count": 1,
                },
            },
            "ehl": {
                "evidence_summary": {"total_spans": 2},
                "hypotheses": [{"kind": "table", "method": "bcs", "selected": True}],
                "quarantine": {"physical_tables": [{"reason": "synthetic"}]},
            },
        },
    }
    if scenario == "empty_without_reason":
        payload["meta"]["conservation"] = {
            "passed": False,
            "error_count": 1,
            "warning_count": 0,
            "issues": [{"code": "empty_tables_without_reason", "severity": "error"}],
            "metrics": {
                "physical_table_count": 0,
                "logical_table_count": 0,
                "logical_row_count": 0,
                "evidence_span_count": 1,
                "hypothesis_count": 0,
            },
        }
        payload["data"]["document"]["pages"][0]["tables"] = []
        payload["data"]["document"]["logical_tables"] = []
        payload["meta"]["ehl"]["hypotheses"] = []
    return payload, {"scenario": scenario}


async def _execute_mirror_geometry_contract(_case: TQGCase) -> tuple[Any, dict[str, Any]]:
    from docmirror.models.entities.parse_result import (
        CellValue,
        LogicalTable,
        PageContent,
        ParseResult,
        ResultStatus,
        TableBlock,
        TableRow,
    )

    cells = [
        [
            CellValue(
                text="A1",
                bbox=[10, 20, 50, 40],
                row_index=0,
                col_index=0,
                geometry_status="exact",
                geometry_source="synthetic",
                token_ids=["tok_r0_c0"],
            ),
            CellValue(
                text="",
                bbox=[50, 20, 90, 40],
                row_index=0,
                col_index=1,
                geometry_status="estimated",
                geometry_source="synthetic",
                geometry_loss_reason="empty_cell_estimated_from_bands",
            ),
            CellValue(
                text="C1",
                bbox=[90, 20, 130, 40],
                row_index=0,
                col_index=2,
                geometry_status="exact",
                geometry_source="synthetic",
                token_ids=["tok_r0_c2"],
            ),
        ],
        [
            CellValue(
                text="A2",
                bbox=[10, 40, 50, 60],
                row_index=1,
                col_index=0,
                geometry_status="exact",
                geometry_source="synthetic",
                token_ids=["tok_r1_c0"],
            ),
            CellValue(
                text="B2",
                bbox=[50, 40, 90, 60],
                row_index=1,
                col_index=1,
                geometry_status="exact",
                geometry_source="synthetic",
                token_ids=["tok_r1_c1"],
            ),
            CellValue(
                text="C2",
                bbox=[90, 40, 130, 60],
                row_index=1,
                col_index=2,
                geometry_status="exact",
                geometry_source="synthetic",
                token_ids=["tok_r1_c2"],
            ),
        ],
    ]
    rows = []
    for ri, row_cells in enumerate(cells):
        refs = []
        for ci, cell in enumerate(row_cells):
            ref = {"page": 1, "table_id": "pt_1_0", "row": ri, "raw_row": ri + 1, "col": ci}
            refs.append(ref)
            cell.source_cell_refs = [ref]
        rows.append(
            TableRow(
                cells=row_cells,
                source_page=1,
                source_physical_id="pt_1_0",
                source_row_index=ri,
                source_cell_refs=refs,
            )
        )
    geometry = {
        "coordinate_system": "pdf_points_top_left",
        "table_bbox": [10, 10, 130, 60],
        "row_bands": [
            {"index": 0, "bbox": [10, 20, 130, 40], "role": "data"},
            {"index": 1, "bbox": [10, 40, 130, 60], "role": "data"},
        ],
        "col_bands": [
            {"index": 0, "bbox": [10, 10, 50, 60]},
            {"index": 1, "bbox": [50, 10, 90, 60]},
            {"index": 2, "bbox": [90, 10, 130, 60]},
        ],
        "merged_cells": [{"row": 0, "col": 1, "rowspan": 1, "colspan": 2, "bbox": [50, 20, 130, 40]}],
    }
    physical = TableBlock(
        table_id="pt_1_0",
        headers=["A", "B", "C"],
        rows=rows,
        page=1,
        bbox=[10, 10, 130, 60],
        extraction_layer="synthetic_geometry",
        metadata={"geometry": geometry},
    )
    logical_rows = [
        TableRow(
            cells=list(row.cells),
            source_page=row.source_page,
            source_physical_id=row.source_physical_id,
            source_row_index=row.source_row_index,
            source_cell_refs=list(row.source_cell_refs),
        )
        for row in rows
    ]
    mirror = ParseResult(
        status=ResultStatus.SUCCESS,
        pages=[PageContent(page_number=1, width=200, height=100, tables=[physical])],
        logical_tables=[
            LogicalTable(
                table_id="lt_0",
                logical_id="lt_0",
                headers=["A", "B", "C"],
                rows=logical_rows,
                row_count=len(logical_rows),
                source_physical_ids=["pt_1_0"],
                source_pages=[1],
            )
        ],
    )
    return mirror, {"scenario": "synthetic_geometry"}


async def _execute_scanned_micro_grid_contract(case: TQGCase) -> tuple[Any, dict[str, Any]]:
    from docmirror.models.entities.parse_result import (
        DocumentEntities,
        PageContent,
        ParseResult,
        ResultStatus,
        TextBlock,
    )
    from docmirror.models.mirror.page_evidence_bundles import (
        domain_specific_with_page_bundles,
        materialize_micro_grids_from_bundles,
        page_evidence_bundle,
    )
    from docmirror.plugins.credit_report.repayment_grid import records_from_micro_grid_dict

    if "negative" in case.id:
        lines = [
            {"content": "个人消费贷款", "bbox": [80.0, 120.0, 200.0, 140.0], "confidence": 1.0},
            {"content": "NN N N", "bbox": [300.0, 180.0, 520.0, 200.0], "confidence": 1.0},
            {"content": "000 0", "bbox": [300.0, 210.0, 520.0, 230.0], "confidence": 1.0},
        ]
    else:
        lines = [
            {"content": "2020年09月-2021年02月的还款记录", "bbox": [280.46, 194.67, 510.65, 217.78], "confidence": 1.0},
            {"content": "1 122689 113.45710", "bbox": [130.84, 222.65, 733.57, 241.51], "confidence": 1.0},
            {"content": "CN.", "bbox": [136.90, 249.42, 206.56, 267.06], "confidence": 1.0},
            {"content": "2021", "bbox": [75.71, 262.80, 112.67, 280.44], "confidence": 1.0},
            {"content": "NN N N", "bbox": [559.11, 302.34, 731.75, 319.38], "confidence": 1.0},
            {"content": "2020", "bbox": [75.11, 315.12, 109.64, 332.76], "confidence": 1.0},
            {"content": "000 0", "bbox": [561.53, 327.89, 729.93, 345.54], "confidence": 1.0},
        ]
    ds = domain_specific_with_page_bundles(
        page_evidence_bundle(
            4,
            micro_grid_evidence={"page": 4, "lines": lines, "tokens": []},
        ),
    )
    materialize_micro_grids_from_bundles(ds)
    grids = ds["_page_evidence_bundles"][0].get("micro_grid_structures") or []
    records: list[dict[str, Any]] = []
    for grid in grids:
        records.extend(records_from_micro_grid_dict(grid))
    ds["credit_repayment_records"] = records
    mirror = ParseResult(
        status=ResultStatus.SUCCESS,
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=ds,
        ),
        pages=[
            PageContent(
                page_number=4,
                texts=[TextBlock(content=line["content"], bbox=line["bbox"]) for line in lines],
                width=834,
                height=1207,
            )
        ],
    )
    return mirror, {"scenario": "synthetic_scanned_micro_grid"}


async def _execute_scanned_local_structure_contract(case: TQGCase) -> tuple[Any, dict[str, Any]]:
    from docmirror.models.entities.parse_result import (
        DocumentEntities,
        PageContent,
        ParseResult,
        ResultStatus,
        TextBlock,
    )
    from docmirror.ocr.local_structure import extract_local_structure_evidence
    from docmirror.plugins.credit_report.account_structure import extract_credit_accounts_from_local_structure_evidence

    if "negative" in case.id:
        lines = [
            {"content": "文档说明", "bbox": [20.0, 20.0, 100.0, 38.0], "confidence": 1.0},
            {"content": "这是一段普通说明文本", "bbox": [20.0, 55.0, 240.0, 72.0], "confidence": 1.0},
        ]
    else:
        lines = [
            {"content": "账户2", "bbox": [20.0, 10.0, 70.0, 24.0], "confidence": 1.0},
            {"content": "管理机构 账户标识 开立日期", "bbox": [20.0, 40.0, 320.0, 54.0], "confidence": 1.0},
            {
                "content": "重庆市蚂蚁商诚信 蚂蚁借呗合并SYNTHETIC_ACCOUNT_REF 2018.08.31",
                "bbox": [20.0, 60.0, 520.0, 74.0],
                "confidence": 1.0,
            },
            {"content": "账户币种 到期日期 借款金额", "bbox": [20.0, 90.0, 320.0, 104.0], "confidence": 1.0},
            {"content": "人民币 2019.06.21 72,000", "bbox": [20.0, 110.0, 320.0, 124.0], "confidence": 1.0},
            {"content": "业务种类 担保方式 账户状态 关闭日期", "bbox": [20.0, 140.0, 420.0, 154.0], "confidence": 1.0},
            {
                "content": "其他个人消费贷款 信用/免担保 结清 2019.06.21",
                "bbox": [20.0, 160.0, 420.0, 174.0],
                "confidence": 1.0,
            },
        ]
    evidence = extract_local_structure_evidence(lines, page=4, page_width=834, page_height=1207)
    account_out = extract_credit_accounts_from_local_structure_evidence(
        [{"page": 4, "structures": evidence.get("structures") or []}]
    )
    mirror = ParseResult(
        status=ResultStatus.SUCCESS,
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=_local_structure_bundle_domain(
                page=4,
                page_width=834,
                page_height=1207,
                lines=lines,
                evidence=evidence,
                credit_accounts=account_out.get("credit_accounts") or [],
            ),
        ),
        pages=[
            PageContent(
                page_number=4,
                texts=[TextBlock(content=line["content"], bbox=line["bbox"]) for line in lines],
                width=834,
                height=1207,
            )
        ],
    )
    return mirror, {"scenario": "synthetic_scanned_local_structure"}


async def _execute_scanned_local_structure_realistic_fixture(_case: TQGCase) -> tuple[Any, dict[str, Any]]:
    import json
    from pathlib import Path

    from docmirror.models.entities.parse_result import (
        DocumentEntities,
        PageContent,
        ParseResult,
        ResultStatus,
        TextBlock,
    )
    from docmirror.ocr.local_structure import extract_local_structure_evidence
    from docmirror.plugins.credit_report.account_structure import extract_credit_accounts_from_local_structure_evidence

    fixture_path = Path("tests/fixtures/scanned/account_card_page4_layout.json")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    lines = [
        {"content": line["content"], "bbox": line["bbox"], "confidence": line.get("confidence", 1.0)}
        for line in fixture.get("lines") or []
    ]
    page = int(fixture.get("page") or 4)
    page_width = int(float(fixture.get("page_width") or 834))
    page_height = int(float(fixture.get("page_height") or 1207))
    evidence = extract_local_structure_evidence(
        lines,
        tokens=fixture.get("tokens") or [],
        page=page,
        page_width=page_width,
        page_height=page_height,
    )
    account_out = extract_credit_accounts_from_local_structure_evidence(
        [{"page": page, "structures": evidence.get("structures") or []}]
    )
    mirror = ParseResult(
        status=ResultStatus.SUCCESS,
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=_local_structure_bundle_domain(
                page=page,
                page_width=page_width,
                page_height=page_height,
                lines=lines,
                evidence=evidence,
                credit_accounts=account_out.get("credit_accounts") or [],
            ),
        ),
        pages=[
            PageContent(
                page_number=page,
                texts=[TextBlock(content=line["content"], bbox=line["bbox"]) for line in lines],
                width=page_width,
                height=page_height,
            )
        ],
    )
    return mirror, {"scenario": "realistic_scanned_local_structure_fixture"}


async def _execute_scanned_local_structure_full_page_fixture(_case: TQGCase) -> tuple[Any, dict[str, Any]]:
    import json
    from pathlib import Path

    from docmirror.models.entities.parse_result import (
        DocumentEntities,
        PageContent,
        ParseResult,
        ResultStatus,
        TextBlock,
    )
    from docmirror.ocr.local_structure import extract_local_structure_evidence
    from docmirror.plugins.credit_report.account_structure import extract_credit_accounts_from_local_structure_evidence

    fixture_path = Path("tests/fixtures/scanned/account_card_page4_full_layout.json")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    lines = [
        {"content": line["content"], "bbox": line["bbox"], "confidence": line.get("confidence", 1.0)}
        for line in fixture.get("lines") or []
    ]
    page = int(fixture.get("page") or 4)
    page_width = int(float(fixture.get("page_width") or 834))
    page_height = int(float(fixture.get("page_height") or 1207))
    evidence = extract_local_structure_evidence(
        lines,
        tokens=fixture.get("tokens") or [],
        page=page,
        page_width=float(fixture.get("page_width") or page_width),
        page_height=float(fixture.get("page_height") or page_height),
    )
    account_out = extract_credit_accounts_from_local_structure_evidence(
        [{"page": page, "structures": evidence.get("structures") or []}]
    )
    mirror = ParseResult(
        status=ResultStatus.SUCCESS,
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=_local_structure_bundle_domain(
                page=page,
                page_width=page_width,
                page_height=page_height,
                lines=lines,
                evidence=evidence,
                credit_accounts=account_out.get("credit_accounts") or [],
            ),
        ),
        pages=[
            PageContent(
                page_number=page,
                texts=[TextBlock(content=line["content"], bbox=line["bbox"]) for line in lines],
                width=page_width,
                height=page_height,
            )
        ],
    )
    return mirror, {"scenario": "full_page_scanned_local_structure_fixture"}


def _primary_logical_rows(result: Any) -> int:
    return mirror_expected_primary_rows(result)


def _logical_row_count(result: Any) -> int:
    logical = get_logical_tables(result)
    return sum(lt.row_count for lt in logical) if logical else 0


def _merged_logical_primary_rows(result: Any) -> int:
    logical = get_logical_tables(result)
    merged = [lt for lt in logical if len(lt.source_pages or []) >= 2]
    if not merged:
        return 0
    primary = max(merged, key=lambda lt: lt.row_count)
    return primary.row_count


def _table_rows_from_base(meta: dict[str, Any]) -> int:
    base = meta.get("base")
    if base is None:
        return 0
    return sum(
        len(b.raw_content)
        for pg in base.pages
        for b in pg.blocks
        if b.block_type == "table" and isinstance(b.raw_content, list)
    )


def _edition_total_rows(edition: dict[str, Any] | None) -> int:
    if not edition:
        return 0
    data = edition.get("data") or {}
    records = data.get("records") or edition.get("records") or []
    if records:
        return len(records)
    summary = data.get("summary") or edition.get("summary") or {}
    return int(summary.get("total_transactions") or summary.get("total_rows") or 0)


def _dec_validation_issues(edition: dict[str, Any] | None) -> list[Any]:
    if not edition:
        return ["missing edition payload"]
    status = edition.get("status") or {}
    errors = list(status.get("errors") or [])
    warnings = [w for w in (status.get("warnings") or []) if isinstance(w, str) and w.startswith("dec_validation:")]
    quality = edition.get("quality") or {}
    if quality.get("validation_passed") is False:
        return errors or warnings or ["validation_passed is false"]
    return errors + warnings


def _resolve_gate_actual(gate_name: str, result: Any, meta: dict[str, Any]) -> Any:
    if gate_name == "document_type":
        entities = getattr(result, "entities", None)
        return getattr(entities, "document_type", "") if entities else ""
    if gate_name == "status":
        status = getattr(result, "status", None)
        return status.value if hasattr(status, "value") else str(status)
    if gate_name == "page_count":
        return meta.get("page_count") or getattr(result, "page_count", 0)
    if gate_name == "table_count":
        return meta.get("table_count") or getattr(result, "total_tables", 0)
    if gate_name == "content_type":
        base = meta.get("base")
        if base is None:
            return None
        pre = base.metadata.get("pre_analysis") or {}
        if pre.get("content_type"):
            return pre.get("content_type")
        structure = base.metadata.get("structure") or {}
        primary = structure.get("primary")
        if primary == "section_led":
            return "section_dominant"
        if primary == "table_led":
            return "table_dominant"
        return None
    if gate_name == "layout_profile_id":
        base = meta.get("base")
        if base is None:
            return None
        return base.metadata.get("layout_profile_id")
    if gate_name == "primary_logical_rows":
        return _primary_logical_rows(result)
    if gate_name == "logical_row_count":
        return _logical_row_count(result)
    if gate_name == "merged_logical_row_count":
        return _merged_logical_primary_rows(result)
    if gate_name == "table_rows":
        return _table_rows_from_base(meta)
    if gate_name == "edition_total_rows":
        edition = meta.get("edition_payload")
        if edition is None and isinstance(result, dict):
            edition = result.get("edition")
        return _edition_total_rows(edition)
    if gate_name == "edition_drift_ratio":
        edition = meta.get("edition_payload")
        if edition is None and isinstance(result, dict):
            edition = result.get("edition")
        mirror = result.get("mirror") if isinstance(result, dict) else result
        primary = _primary_logical_rows(mirror)
        community = _edition_total_rows(edition)
        if primary <= 0:
            return 1.0
        return abs(community - primary) / primary
    if gate_name == "dec_validation":
        edition = meta.get("edition_payload")
        if edition is None and isinstance(result, dict):
            edition = result.get("edition")
        return _dec_validation_issues(edition)
    if gate_name in ("canonical_ratio", "coverage_ratio", "extract_status", "canonical_extracted"):
        edition = meta.get("edition_payload")
        if edition is None and isinstance(result, dict):
            edition = result.get("edition")
        props = ((edition or {}).get("document") or {}).get("properties") or {}
        return props.get(gate_name)
    if gate_name == "plugin_document_type":
        mirror = result.get("mirror") if isinstance(result, dict) else result
        if mirror is not None:
            api = mirror.to_mirror_json_vnext() if hasattr(mirror, "to_mirror_json_vnext") else {}
            meta_block = ((api.get("semantics") or {}).get("views") or {}).get("meta") or {}
            if meta_block.get("plugin_document_type"):
                return meta_block.get("plugin_document_type")
            entities = getattr(mirror, "entities", None)
            domain = getattr(entities, "domain_specific", None) if entities else None
            if isinstance(domain, dict):
                return domain.get("plugin_document_type")
        return None
    if gate_name == "warning_contains":
        return meta.get("edition_warnings") or []
    if gate_name in ("is_entitled", "lifecycle_state", "has_license_warning", "premium_feature", "lifecycle_days"):
        return meta.get(gate_name)
    if gate_name == "row_preservation_ratio":
        return meta.get("row_preservation_ratio")
    if gate_name in meta:
        return meta[gate_name]
    if isinstance(result, dict) and gate_name in result:
        return result[gate_name]
    return resolve_dot_path(result, gate_name)


def _run_oracle(case: TQGCase, meta: dict[str, Any], profile_id: str | None) -> tuple[int, GateReport]:
    oracle_report = GateReport(case_id=case.id, track=case.track, tier=case.tier)
    oracle_spec = case.oracle or {}
    mode = oracle_spec.get("mode")
    profile = GATE_PROFILES.get(profile_id or "", GATE_PROFILES["generic"])
    sample_pages = int(oracle_spec.get("sample_pages") or profile.oracle_sample_pages)
    page_count = int(meta.get("page_count") or 0)
    if mode == "pdfplumber_full_page_sample" or (
        profile.oracle_mode.value == "pdfplumber_full_page_sample" and case.fixture
    ):
        try:
            oracle_rows = pdfplumber_full_page_sample_oracle(
                case.fixture,
                num_pages=page_count or None,
                sample_count=sample_pages,
            )
        except Exception as exc:
            oracle_report.passed = False
            oracle_report.failures.append(f"oracle failed: {exc}")
            return 0, oracle_report
        oracle_report.metrics["oracle_row_count"] = oracle_rows
        return oracle_rows, oracle_report
    return 0, oracle_report


def _merge_gate_result(report: GateReport, gate_result: Any) -> None:
    report.checks.update(gate_result.checks)
    report.failures.extend(gate_result.failures)
    report.metrics.update(gate_result.metrics)
    if gate_result.failure_class and not report.failure_class:
        report.failure_class = gate_result.failure_class
    if not gate_result.passed:
        report.passed = False


async def run_tqg_case_async(case: TQGCase) -> GateReport:
    report = GateReport(case_id=case.id, track=case.track, tier=case.tier)

    if case.fixture and not case.fixture.is_file():
        if case.skip_if_fixture_missing:
            report.passed = False
            report.failures.append(f"fixture missing: {case.fixture}")
            return report
        report.failures.append(f"fixture missing: {case.fixture}")
        report.passed = False
        return report

    pipeline = case.pipeline
    if pipeline == "extract_only":
        result, meta = await _execute_extract_only(case)
    elif pipeline == "classify_text":
        result, meta = await _execute_classify_text(case)
    elif pipeline == "transport_capability":
        result, meta = await _execute_transport_capability(case)
    elif pipeline == "transport_dispatch":
        result, meta = await _execute_transport_dispatch(case)
    elif pipeline == "e2e_four_file":
        result, meta = await _execute_e2e_four_file(case)
    elif pipeline == "e2e_contract":
        result, meta = await _execute_e2e_contract(case)
    elif pipeline == "mirror_conservation_contract":
        result, meta = await _execute_mirror_conservation_contract(case)
    elif pipeline == "mirror_geometry_contract":
        result, meta = await _execute_mirror_geometry_contract(case)
    elif pipeline == "scanned_micro_grid_contract":
        result, meta = await _execute_scanned_micro_grid_contract(case)
    elif pipeline == "scanned_local_structure_contract":
        result, meta = await _execute_scanned_local_structure_contract(case)
    elif pipeline == "scanned_local_structure_realistic_fixture":
        result, meta = await _execute_scanned_local_structure_realistic_fixture(case)
    elif pipeline == "scanned_local_structure_full_page_fixture":
        result, meta = await _execute_scanned_local_structure_full_page_fixture(case)
    elif pipeline == "licensing":
        from docmirror.eval.tqg.licensing_exec import execute_licensing

        result, meta = await execute_licensing(case)
    elif pipeline in ("edition", "full_perceive"):
        result, meta = await _execute_edition(case)
        if case.optional_edition and meta.get("edition_skipped"):
            report.metrics["edition_skipped"] = meta["edition_skipped"]
            return report
    else:
        result, meta = await _execute_perceive(case)

    oracle_rows = 0
    if case.gate_profile or case.oracle:
        oracle_rows, oracle_part = _run_oracle(case, meta, case.gate_profile)
        report.merge(oracle_part)

    if case.gate_profile:
        profile = GATE_PROFILES.get(case.gate_profile)
        if profile:
            mirror_for_gate = result.get("mirror") if isinstance(result, dict) else result
            row_gate = extract_row_preservation_check(
                mirror_for_gate,
                profile=profile,
                oracle_row_count=oracle_rows,
            )
            _merge_gate_result(report, row_gate)
            if row_gate.metrics.get("row_preservation_ratio") is not None:
                meta["row_preservation_ratio"] = row_gate.metrics["row_preservation_ratio"]

    oracle_spec = case.oracle or {}
    if oracle_spec.get("dual_view"):
        mirror_for_dual = result.get("mirror") if isinstance(result, dict) else result
        quarantined = meta.get("quarantined") or []
        dv_spec = oracle_spec.get("dual_view")
        max_secondary = 10
        if isinstance(dv_spec, dict):
            max_secondary = int(dv_spec.get("max_secondary_logical_rows", 10))
        dual = dual_view_consistency_check(
            mirror_for_dual,
            quarantined_tables=quarantined,
            max_secondary_logical_rows=max_secondary,
        )
        _merge_gate_result(report, dual)

    audit_spec = oracle_spec.get("audit")
    if audit_spec:
        from docmirror.eval.tqg.audit_oracle import run_extraction_audit_oracle

        audit_report = run_extraction_audit_oracle(
            meta,
            audit_spec,
            case_id=case.id,
            track=case.track,
            tier=case.tier,
        )
        report.merge(audit_report)

    col_spec = oracle_spec.get("column_fidelity")
    if col_spec:
        from docmirror.eval.tqg.extract_oracles import run_column_fidelity_oracle

        mirror = result.get("mirror") if isinstance(result, dict) else result
        col_report = run_column_fidelity_oracle(
            mirror,
            col_spec,
            case_id=case.id,
            track=case.track,
            tier=case.tier,
        )
        report.merge(col_report)

    quarantine_spec = oracle_spec.get("quarantine_metadata")
    if quarantine_spec:
        from docmirror.eval.tqg.extract_oracles import run_quarantine_metadata_oracle

        q_report = run_quarantine_metadata_oracle(
            meta,
            quarantine_spec,
            case_id=case.id,
            track=case.track,
            tier=case.tier,
        )
        report.merge(q_report)

    text_snapshot_spec = oracle_spec.get("text_snapshot")
    if text_snapshot_spec:
        from docmirror.eval.tqg.extract_oracles import run_text_snapshot_oracle

        ts_report = run_text_snapshot_oracle(
            meta,
            text_snapshot_spec,
            case_id=case.id,
            track=case.track,
            tier=case.tier,
        )
        report.merge(ts_report)

    bank_spec = oracle_spec.get("bank_statement")
    if bank_spec:
        from docmirror.eval.tqg.bank_statement_oracles import run_bank_statement_edition_oracle

        edition = meta.get("edition_payload")
        if edition is None and isinstance(result, dict):
            edition = result.get("edition")
        bs_report = GateReport(case_id=case.id, track=case.track, tier=case.tier)
        run_bank_statement_edition_oracle(edition, bank_spec, bs_report)
        report.merge(bs_report)

    mirror_structure_spec = oracle_spec.get("mirror_structure")
    if mirror_structure_spec:
        from docmirror.eval.tqg.mirror_structure_oracles import run_mirror_structure_oracle

        ms_report = run_mirror_structure_oracle(
            meta,
            mirror_structure_spec,
            case_id=case.id,
            track=case.track,
            tier=case.tier,
        )
        report.merge(ms_report)

    conservation_spec = oracle_spec.get("mirror_conservation")
    if conservation_spec:
        from docmirror.eval.tqg.conservation_oracles import run_mirror_conservation_oracle

        conservation_input = (
            result.get("mirror") if isinstance(result, dict) and result.get("mirror") is not None else result
        )
        mc_report = run_mirror_conservation_oracle(
            conservation_input,
            conservation_spec,
            case_id=case.id,
            track=case.track,
            tier=case.tier,
        )
        report.merge(mc_report)

    geometry_spec = oracle_spec.get("mirror_geometry")
    if geometry_spec:
        from docmirror.eval.tqg.geometry_oracles import run_mirror_geometry_oracle

        mg_report = run_mirror_geometry_oracle(
            result.get("mirror") if isinstance(result, dict) else result,
            geometry_spec,
            case_id=case.id,
            track=case.track,
            tier=case.tier,
        )
        report.merge(mg_report)

    scanned_micro_grid_spec = oracle_spec.get("scanned_micro_grid")
    if scanned_micro_grid_spec:
        from docmirror.eval.tqg.scanned_micro_grid_oracles import run_scanned_micro_grid_oracle

        smg_report = run_scanned_micro_grid_oracle(
            result.get("mirror") if isinstance(result, dict) else result,
            scanned_micro_grid_spec,
            case_id=case.id,
            track=case.track,
            tier=case.tier,
        )
        report.merge(smg_report)

    scanned_local_structure_spec = oracle_spec.get("scanned_local_structure")
    if scanned_local_structure_spec:
        from docmirror.eval.tqg.scanned_local_structure_oracles import run_scanned_local_structure_oracle

        sls_report = run_scanned_local_structure_oracle(
            result.get("mirror") if isinstance(result, dict) else result,
            scanned_local_structure_spec,
            case_id=case.id,
            track=case.track,
            tier=case.tier,
        )
        report.merge(sls_report)

    vnext_page_topology_spec = oracle_spec.get("vnext_page_topology")
    if vnext_page_topology_spec:
        from docmirror.eval.tqg.vnext_page_topology_oracles import run_vnext_page_topology_oracle

        pc_report = run_vnext_page_topology_oracle(
            result.get("mirror") if isinstance(result, dict) else result,
            vnext_page_topology_spec,
            case_id=case.id,
            track=case.track,
            tier=case.tier,
        )
        report.merge(pc_report)

    vnext_finance_spec = oracle_spec.get("vnext_finance")
    if vnext_finance_spec:
        from docmirror.eval.tqg.finance_stability_oracles import run_vnext_finance_stability_oracle

        fin_report = run_vnext_finance_stability_oracle(
            result.get("mirror") if isinstance(result, dict) else result,
            vnext_finance_spec,
            case_id=case.id,
            track=case.track,
            tier=case.tier,
        )
        report.merge(fin_report)

    for gate_name, spec in case.gates.items():
        actual = _resolve_gate_actual(gate_name, result, meta)
        ok, msg = eval_gate(actual, spec)
        report.checks[gate_name] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"{gate_name}: {msg}")

    if case.failure_class:
        report.failure_class = report.failure_class or _failure_class_from_str(case.failure_class)

    if not report.failure_class and not report.passed:
        report.failure_class = FailureClass.TABLE_EXTRACTION

    return report


def run_tqg_case(case: TQGCase) -> GateReport:
    """Run a single TQG manifest case synchronously."""
    return asyncio.run(run_tqg_case_async(case))
