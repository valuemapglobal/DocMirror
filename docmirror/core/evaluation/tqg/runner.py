# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TQG unified runner — manifest cases → GateReport."""

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

from docmirror.core.evaluation.gates import (
    GATE_PROFILES,
    FailureClass,
    dual_view_consistency_check,
    extract_row_preservation_check,
)
from docmirror.core.evaluation.oracle import pdfplumber_full_page_sample_oracle
from docmirror.core.evaluation.tqg.gates_eval import eval_gate, resolve_dot_path
from docmirror.core.evaluation.tqg.manifest import TQGCase
from docmirror.core.evaluation.tqg.report import GateReport
from docmirror.core.extraction.extractor import CoreExtractor
from docmirror.core.factory import PerceiveOptions, perceive_document
from docmirror.core.table.table_access import get_logical_tables
from docmirror.models.construction.parse_result_bridge import ParseResultBridge

logger = logging.getLogger(__name__)

_PLUGIN_MODULES: dict[str, str] = {
    "wechat_payment": "docmirror.plugins.wechat_payment_community",
    "alipay_payment": "docmirror.plugins.alipay_payment_community",
    "bank_statement": "docmirror.plugins.bank_statement_community",
}


def _failure_class_from_str(name: str | None) -> FailureClass | None:
    if not name:
        return None
    try:
        return FailureClass(name)
    except ValueError:
        return FailureClass.UNKNOWN


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
        }
        return result, meta
    finally:
        if opts.get("max_pages"):
            os.environ.pop("DOCMIRROR_MAX_PAGES", None)


async def _execute_classify_text(case: TQGCase) -> tuple[Any, dict[str, Any]]:
    """Run EvidenceEngine on a keyword-rich text fixture (no full extraction)."""
    from docmirror.core.classification.evidence_engine import EvidenceEngine
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
    perceive_result = await perceive_document(case.fixture, perceive_opts)
    mirror = perceive_result.mirror
    meta: dict[str, Any] = {
        "perceive_result": perceive_result,
        "page_count": mirror.page_count,
        "table_count": mirror.total_tables,
    }
    return mirror, meta


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
    perceive_result = meta.get("perceive_result")
    edition_payload: dict[str, Any] | None = None
    if perceive_result and getattr(perceive_result, "editions", None):
        edition_payload = perceive_result.editions.get(edition_name)
    if edition_payload is None:
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
    from docmirror.core.perceive_result import PerceiveResult
    from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
    from docmirror.server.edition_outputs import build_all_edition_outputs

    contract = str(case.options.get("contract", ""))
    passed = False
    if contract == "perceive_result_envelope":
        mirror = ParseResult(status=ResultStatus.SUCCESS)
        mirror.entities = DocumentEntities(document_type="business_license")
        env = PerceiveResult(mirror=mirror, editions={"community": {"edition": "community"}})
        passed = (
            env.mirror is mirror
            and env.editions["community"]["edition"] == "community"
            and "_edition_outputs" not in (mirror.entities.domain_specific or {})
        )
    elif contract == "enterprise_not_generated":
        mirror = ParseResult(status=ResultStatus.SUCCESS)
        mirror.entities = DocumentEntities(document_type="business_license")
        try:
            importlib.import_module("docmirror_enterprise")
        except ImportError:
            outputs = build_all_edition_outputs(mirror)
            passed = outputs.get("enterprise") is None
        else:
            passed = True
    return {"contract_passed": passed}, {"contract_passed": passed}


def _primary_logical_rows(result: Any) -> int:
    logical = get_logical_tables(result)
    if not logical:
        return 0
    return max(lt.row_count for lt in logical)


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
    errors = status.get("errors") or []
    quality = edition.get("quality") or {}
    if quality.get("validation_passed") is False:
        return errors or ["validation_passed is false"]
    return errors


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
        return pre.get("content_type")
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
        dual = dual_view_consistency_check(
            mirror_for_dual,
            quarantined_tables=meta.get("quarantined"),
        )
        _merge_gate_result(report, dual)

    audit_spec = oracle_spec.get("audit")
    if audit_spec:
        from docmirror.core.evaluation.tqg.audit_oracle import run_extraction_audit_oracle

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
        from docmirror.core.evaluation.tqg.extract_oracles import run_column_fidelity_oracle

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
        from docmirror.core.evaluation.tqg.extract_oracles import run_quarantine_metadata_oracle

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
        from docmirror.core.evaluation.tqg.extract_oracles import run_text_snapshot_oracle

        ts_report = run_text_snapshot_oracle(
            meta,
            text_snapshot_spec,
            case_id=case.id,
            track=case.track,
            tier=case.tier,
        )
        report.merge(ts_report)

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
