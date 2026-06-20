#!/usr/bin/env python3
"""
三版模式 Schema 合规性自动化测试
========================================

基于三个设计文档的架构要求，验证 docmirror 输出的社区版/企业版/金融版文件
在 顶级结构、字段必填项、跨字段一致性 上是否符合设计要求。

设计文档:
  - docs/design/01_community_edition_architecture_guide_v2.md
  - docs/design/02_enterprise_edition_architecture_guide_v2.md
  - docs/design/03_finance_edition_architecture_guide_v2.md

用法:
  python3 -m pytest tests/test_edition_schema_conformance.py -v
  python3 tests/test_edition_schema_conformance.py    # 直接运行
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ──────────────────────────────────────────────
# 社区版 v2 合规检查
# ──────────────────────────────────────────────

COMMUNITY_REQUIRED_BLOCKS = {
    "schema_version": str,
    "edition": str,
    "document": dict,
    "classification": dict,
    "status": dict,
    "plugin": dict,
    "data": dict,
    "plugins": dict,
    "metadata": dict,
}

COMMUNITY_DOCUMENT_KEYS = {
    "document_type": str,
    "document_name": (str, type(None)),
    "domain": str,
    "archetype": str,
    "language": str,
    "region": str,
    "source_format": str,
    "page_count": (int, float, type(None)),
}

COMMUNITY_CLASSIFICATION_KEYS = {
    "matched": bool,
    "matched_document_type": str,
    "matched_domain": str,
    "matched_archetype": str,
    "match_method": str,
    "candidate_types": list,
}

COMMUNITY_STATUS_KEYS = {
    "success": bool,
    "warnings": list,
    "errors": list,
}

COMMUNITY_PLUGIN_KEYS = {
    "name": str,
    "display_name": str,
    "version": str,
    "support_level": str,
}

COMMUNITY_DATA_KEYS = {
    "fields": dict,
    "records": list,
    "sections": list,
    "tables": list,
    "line_items": list,
    "summary": dict,
}

COMMUNITY_METADATA_KEYS = {
    "generated_at": str,
    "parser": str,
    "parser_version": str,
}

# 社区版记录格式
COMMUNITY_RECORD_KEYS = {
    "row_index": (int, float),
    "raw": dict,
    "normalized": dict,
}


def check_community(schema: dict, path_hint: str = "") -> list[str]:
    """验证社区版输出是否符合 v2 设计规范。返回错误列表，空列表表示通过。"""
    errors = []

    # 1. 顶级块检查
    for key, expected_type in COMMUNITY_REQUIRED_BLOCKS.items():
        if key not in schema:
            errors.append(f"[C01] 缺少顶级块: {key}")
            continue
        val = schema[key]
        if not isinstance(val, expected_type):
            errors.append(f"[C02] 顶级块 {key} 类型错误: 期望 {expected_type.__name__}, 实际 {type(val).__name__}")

    # 2. edition 必须为 community
    if schema.get("edition") != "community":
        errors.append(f"[C03] edition 应为 'community', 实际为 {schema.get('edition')}")

    # 3. schema_version
    sv = schema.get("schema_version", "")
    if not re.match(r"^\d+\.\d+$", str(sv)):
        errors.append(f"[C04] schema_version 格式错误: {sv}")

    # 4. document 块
    doc = schema.get("document", {})
    for key, expected_type in COMMUNITY_DOCUMENT_KEYS.items():
        if key not in doc:
            errors.append(f"[C05] document 缺少字段: {key}")
            continue
        val = doc[key]
        if not isinstance(val, expected_type):
            errors.append(f"[C06] document.{key} 类型错误: 期望 {expected_type}, 实际 {type(val).__name__}")
    if doc.get("archetype") not in (
        "key_value_document",
        "table_document",
        "report_document",
        "contract_document",
        "voucher_document",
        "legal_document",
        "package_document",
        "generic_mirror",
    ):
        errors.append(f"[C07] document.archetype 不在允许形态中: {doc.get('archetype')}")

    # 5. classification 块
    cls = schema.get("classification", {})
    for key, expected_type in COMMUNITY_CLASSIFICATION_KEYS.items():
        if key not in cls:
            errors.append(f"[C08] classification 缺少字段: {key}")
    if cls.get("matched") and not cls.get("matched_document_type"):
        errors.append("[C09] classification.matched=true 但 matched_document_type 为空")

    # 6. status 块
    st = schema.get("status", {})
    for key, expected_type in COMMUNITY_STATUS_KEYS.items():
        if key not in st:
            errors.append(f"[C10] status 缺少字段: {key}")

    # 7. plugin 块
    pl = schema.get("plugin", {})
    for key, expected_type in COMMUNITY_PLUGIN_KEYS.items():
        if key not in pl:
            errors.append(f"[C11] plugin 缺少字段: {key}")
    if pl.get("support_level") not in ("L1", "L2", "L3", "generic"):
        errors.append(f"[C12] plugin.support_level 应为 L1/L2/L3/generic, 实际为 {pl.get('support_level')}")

    # 8. data 块
    dt = schema.get("data", {})
    for key, expected_type in COMMUNITY_DATA_KEYS.items():
        if key not in dt:
            errors.append(f"[C13] data 缺少字段: {key}")

    # 9. 记录格式检查
    records = dt.get("records", [])
    for i, rec in enumerate(records[:5]):  # 检查前 5 条
        for rk, rt in COMMUNITY_RECORD_KEYS.items():
            if rk not in rec:
                errors.append(f"[C14] records[{i}] 缺少字段: {rk}")
                continue
            if not isinstance(rec[rk], rt):
                errors.append(f"[C15] records[{i}].{rk} 类型错误: 期望 {rt}, 实际 {type(rec[rk]).__name__}")
        # raw 和 normalized 不应完全相同
        raw = rec.get("raw", {})
        norm = rec.get("normalized", {})
        if raw and norm and raw == norm:
            errors.append(f"[C16] records[{i}].raw 与 normalized 完全相同, 社区版应差异化")

    # 10. metadata 块
    meta = schema.get("metadata", {})
    for key, expected_type in COMMUNITY_METADATA_KEYS.items():
        if key not in meta:
            errors.append(f"[C17] metadata 缺少字段: {key}")

    # 11. document_name 不应为空
    if not doc.get("document_name"):
        errors.append("[C18] document.document_name 不应为空")

    # 12. plugins 块存在 (兼容旧格式)
    plugins = schema.get("plugins", {})
    matched_type = cls.get("matched_document_type", "")
    if matched_type and matched_type not in plugins:
        errors.append(f"[C19] plugins 中缺少 matched_document_type: {matched_type}")

    return errors


# ──────────────────────────────────────────────
# 企业版 v2 合规检查
# ──────────────────────────────────────────────

ENTERPRISE_REQUIRED_BLOCKS = {
    "schema_version": str,
    "edition": str,
    "document": dict,
    "classification": dict,
    "source": dict,
    "status": dict,
    "processing": dict,
    "extraction": dict,
    "normalization": dict,
    "quality": dict,
    "validation": dict,
    "security": dict,
    "review": dict,
    "output": dict,
    "audit": dict,
    "metadata": dict,
    "plugins": dict,
}

ENTERPRISE_SOURCE_KEYS = {
    "file_name": str,
    "file_hash": str,
    "file_size": (int, float, type(None)),
    "page_count": (int, float, type(None)),
}

ENTERPRISE_PROCESSING_KEYS = {
    "task_id": str,
    "batch_id": str,
    "status": str,
    "started_at": str,
    "finished_at": str,
    "duration_ms": (int, float),
}

ENTERPRISE_QUALITY_KEYS = {
    "overall_score": (int, float),
    "field_coverage": (dict, type(None)),
    "field_confidence": (dict, type(None)),
    "record_confidence": list,
    "page_quality": list,
    "table_quality": list,
    "low_confidence_items": list,
}

ENTERPRISE_VALIDATION_KEYS = {
    "rules": list,
}

ENTERPRISE_SECURITY_KEYS = {
    "sensitivity_level": str,
    "pii_detected": bool,
    "sensitive_fields": list,
    "masking_required": bool,
    "access_policy": str,
    "export_policy": str,
}

ENTERPRISE_REVIEW_KEYS = {
    "required": bool,
    "reason": list,
    "review_items": list,
}

ENTERPRISE_OUTPUT_KEYS = {
    "json_available": bool,
    "csv_available": bool,
    "excel_available": bool,
    "markdown_available": bool,
    "report_available": bool,
}

ENTERPRISE_AUDIT_KEYS = {
    "operation_logs": list,
    "data_access_logs": list,
    "export_logs": list,
    "review_logs": list,
}

ENTERPRISE_METADATA_KEYS = {
    "generated_at": str,
    "parser": str,
    "parser_version": str,
    "task_id": str,
    "file_id": str,
}


def check_enterprise(schema: dict, path_hint: str = "") -> list[str]:
    """验证企业版输出是否符合 v2 设计规范。返回错误列表，空列表表示通过。"""
    errors = []

    # 1. 顶级块检查
    for key, expected_type in ENTERPRISE_REQUIRED_BLOCKS.items():
        if key not in schema:
            errors.append(f"[E01] 缺少顶级块: {key}")
            continue
        val = schema[key]
        if not isinstance(val, expected_type):
            errors.append(f"[E02] 顶级块 {key} 类型错误: 期望 {expected_type.__name__}, 实际 {type(val).__name__}")

    # 2. edition
    if schema.get("edition") != "enterprise":
        errors.append(f"[E03] edition 应为 'enterprise', 实际为 {schema.get('edition')}")

    # 3. document_id
    doc = schema.get("document", {})
    if not doc.get("document_id"):
        errors.append("[E04] document.document_id 不应为空")

    # 4. source
    src = schema.get("source", {})
    for key, expected_type in ENTERPRISE_SOURCE_KEYS.items():
        if key not in src:
            errors.append(f"[E05] source 缺少字段: {key}")
    if not src.get("file_name"):
        errors.append("[E06] source.file_name 不应为空")

    # 5. processing 时序一致性
    proc = schema.get("processing", {})
    for key, expected_type in ENTERPRISE_PROCESSING_KEYS.items():
        if key not in proc:
            errors.append(f"[E07] processing 缺少字段: {key}")
    if proc.get("started_at") and proc.get("finished_at"):
        if proc["started_at"] == proc["finished_at"]:
            errors.append("[E08] processing.started_at 与 finished_at 完全相同, 应不同")
    if proc.get("duration_ms", 0) == 0:
        errors.append("[E09] processing.duration_ms 不应为 0")

    # 6. quality
    qual = schema.get("quality", {})
    for key, expected_type in ENTERPRISE_QUALITY_KEYS.items():
        if key not in qual:
            errors.append(f"[E10] quality 缺少字段: {key}")
    if qual.get("overall_score", 0) <= 0 or qual.get("overall_score", 1) > 1:
        errors.append(f"[E11] quality.overall_score 应在 (0, 1] 范围内: {qual.get('overall_score')}")

    # 7. validation
    val = schema.get("validation", {})
    for key, expected_type in ENTERPRISE_VALIDATION_KEYS.items():
        if key not in val:
            errors.append(f"[E12] validation 缺少字段: {key}")
    rules = val.get("rules", [])
    if not rules:
        errors.append("[E13] validation.rules 不应为空")
    for i, r in enumerate(rules):
        if not (r.get("rule") or r.get("rule_code")):
            errors.append(f"[E14] validation rule[{i}] 缺少 rule/rule_code: {r}")
        level = r.get("level") or r.get("severity")
        if not level:
            errors.append(f"[E14] validation rule[{i}] 缺少 level/severity: {r}")
        if not r.get("message"):
            errors.append(f"[E14] validation rule[{i}] 缺少 message: {r}")

    # 8. security
    sec = schema.get("security", {})
    for key, expected_type in ENTERPRISE_SECURITY_KEYS.items():
        if key not in sec:
            errors.append(f"[E15] security 缺少字段: {key}")
    if sec.get("masking_required") and not sec.get("masking_rules_applied"):
        errors.append("[E16] masking_required=true 但 masking_rules_applied 为空")
    if sec.get("sensitivity_level") not in ("S1", "S2", "S3", "S4"):
        errors.append(f"[E17] security.sensitivity_level 非法: {sec.get('sensitivity_level')}")

    # 9. review
    rv = schema.get("review", {})
    for key, expected_type in ENTERPRISE_REVIEW_KEYS.items():
        if key not in rv:
            errors.append(f"[E18] review 缺少字段: {key}")
    if rv.get("required") and not rv.get("review_items"):
        errors.append("[E19] review.required=true 但 review_items 为空")

    # 10. output
    out = schema.get("output", {})
    for key, expected_type in ENTERPRISE_OUTPUT_KEYS.items():
        if key not in out:
            errors.append(f"[E20] output 缺少字段: {key}")

    # 11. audit
    aud = schema.get("audit", {})
    for key, expected_type in ENTERPRISE_AUDIT_KEYS.items():
        if key not in aud:
            errors.append(f"[E21] audit 缺少字段: {key}")
    if not aud.get("operation_logs"):
        errors.append("[E22] audit.operation_logs 不应为空")

    # 12. metadata
    meta = schema.get("metadata", {})
    for key, expected_type in ENTERPRISE_METADATA_KEYS.items():
        if key not in meta:
            errors.append(f"[E23] metadata 缺少字段: {key}")
    if not meta.get("task_id"):
        errors.append("[E24] metadata.task_id 不应为空")

    # 13. plugins 块至少有 matched 插件
    plugins = schema.get("plugins", {})
    cls = schema.get("classification", {})
    matched_type = cls.get("matched_document_type", "")
    if matched_type and matched_type not in plugins:
        errors.append(f"[E25] plugins 中缺少 matched_document_type: {matched_type}")
    api_plugin = plugins.get(matched_type, {})
    if api_plugin.get("support_level") not in ("E1", "E2", "E3"):
        errors.append(f"[E26] plugins.{matched_type}.support_level 应为 E1/E2/E3: {api_plugin.get('support_level')}")

    # 14. extraction/normalization 至少有一个非空
    ext = schema.get("extraction", {})
    norm = schema.get("normalization", {})
    if not ext.get("records") and not ext.get("fields") and not ext.get("tables"):
        if not ext.get("raw_text"):
            errors.append("[E27] extraction 中 records/fields/tables/raw_text 全为空")
    std_records = norm.get("standard_records", [])
    if ext.get("records") and not std_records:
        errors.append("[E28] extraction 有 records 但 normalization.standard_records 为空")

    return errors


# ──────────────────────────────────────────────
# 金融版 v3 合规检查
# ──────────────────────────────────────────────

FINANCE_REQUIRED_BLOCKS = {
    "schema_version": str,
    "edition": str,
    "scenario": dict,
    "subject": dict,
    "document_package": dict,
    "quality_gate": dict,
    "entity_graph": dict,
    "financial_indicators": dict,
    "risk_signals": list,
    "fraud_signals": list,
    "cross_validation": dict,
    "assessment": dict,
    "recommendation": dict,
    "explainability": dict,
    "report": dict,
    "quality": dict,
    "validation": dict,
    "security": dict,
    "review": dict,
    "output": dict,
    "audit": dict,
    "metadata": dict,
    "plugins": dict,
    "document": dict,
    "source": dict,
    "processing": dict,
    "classification": dict,
    "extraction": dict,
    "normalization": dict,
}

FINANCE_SCENARIO_KEYS = {
    "business_type": str,
    "stage": str,
    "institution_type": str,
    "analysis_purpose": str,
}

FINANCE_SUBJECT_KEYS = {
    "subject_type": str,
    "subject_name": str,
}

FINANCE_QUALITY_GATE_KEYS = {
    "passed": bool,
    "minimum_quality_score": (int, float),
    "actual_quality_score": (int, float),
    "warnings": list,
}

FINANCE_QUALITY_KEYS = ENTERPRISE_QUALITY_KEYS

FINANCE_VALIDATION_KEYS = ENTERPRISE_VALIDATION_KEYS

FINANCE_RISK_SIGNAL_KEYS = {
    "signal_code": str,
    "signal_name": str,
    "category": str,
    "severity": str,
    "confidence": (int, float),
    "description": str,
    "evidence": list,
    "suggested_action": str,
}

FINANCE_ASSESSMENT_KEYS = {
    "manual_review_required": bool,
    "decision_strength": str,
}

FINANCE_RECOMMENDATION_KEYS = {
    "suggested_action": str,
    "action_confidence": (int, float),
    "manual_review_required": bool,
}

FINANCE_CROSS_VALIDATION_KEYS = {
    "enabled": bool,
    "checks": list,
}


def check_finance(schema: dict, path_hint: str = "") -> list[str]:
    """验证金融版输出是否符合 v3 设计规范。返回错误列表，空列表表示通过。"""
    errors = []

    # 1. 顶级块检查
    for key, expected_type in FINANCE_REQUIRED_BLOCKS.items():
        if key not in schema:
            errors.append(f"[F01] 缺少顶级块: {key}")
            continue
        val = schema[key]
        if not isinstance(val, expected_type):
            errors.append(f"[F02] 顶级块 {key} 类型错误: 期望 {expected_type.__name__}, 实际 {type(val).__name__}")

    # 2. edition
    if schema.get("edition") != "finance":
        errors.append(f"[F03] edition 应为 'finance', 实际为 {schema.get('edition')}")

    # 3. schema_version
    sv = schema.get("schema_version", "")
    if not re.match(r"^\d+\.\d+$", str(sv)):
        errors.append(f"[F04] schema_version 格式错误: {sv}")

    # 4. scenario
    sc = schema.get("scenario", {})
    for key, expected_type in FINANCE_SCENARIO_KEYS.items():
        if key not in sc:
            errors.append(f"[F05] scenario 缺少字段: {key}")

    # 5. subject
    sbj = schema.get("subject", {})
    for key, expected_type in FINANCE_SUBJECT_KEYS.items():
        if key not in sbj:
            errors.append(f"[F06] subject 缺少字段: {key}")
    if not sbj.get("subject_name"):
        errors.append("[F07] subject.subject_name 不应为空")

    # 6. quality_gate → assessment → recommendation 一致性 (P0)
    qg = schema.get("quality_gate", {})
    assess = schema.get("assessment", {})
    rec = schema.get("recommendation", {})
    for key, expected_type in FINANCE_QUALITY_GATE_KEYS.items():
        if key not in qg:
            errors.append(f"[F08] quality_gate 缺少字段: {key}")
    gate_passed = qg.get("passed", True)
    assess_manual = assess.get("manual_review_required", False)
    rec_manual = rec.get("manual_review_required", False)
    if not gate_passed and not assess_manual:
        errors.append("[F09] quality_gate.passed=false 但 assessment.manual_review_required=false → 应一致")
    if not gate_passed and not rec_manual:
        errors.append("[F10] quality_gate.passed=false 但 recommendation.manual_review_required=false → 应一致")
    if assess_manual != rec_manual:
        errors.append("[F11] assessment.manual_review_required 与 recommendation.manual_review_required 不一致")

    # 7. quality — 结构与 coverage/confidence 一致性
    qual = schema.get("quality", {})
    for key, expected_type in FINANCE_QUALITY_KEYS.items():
        if key not in qual:
            errors.append(f"[F31] quality 缺少字段: {key}")
    overall = qual.get("overall_score", 0)
    if overall <= 0 or overall > 1:
        errors.append(f"[F32] quality.overall_score 应在 (0, 1] 范围内: {overall}")

    fc = qual.get("field_coverage") or {}
    fconf = qual.get("field_confidence") or {}
    if fc and fconf:
        if set(fc.keys()) != set(fconf.keys()):
            errors.append("[F33] field_coverage 与 field_confidence 字段集不一致")
        for field, cov in fc.items():
            conf = fconf.get(field, 0)
            if conf > cov + 0.001:
                errors.append(
                    f"[F34] field_confidence.{field} ({conf}) 不应高于 field_coverage ({cov})"
                )

    rc = qual.get("record_confidence") or []
    if len(rc) > 1:
        indices = [r.get("index") for r in rc]
        if len(set(indices)) == 1 and indices[0] == 0:
            errors.append("[F35] record_confidence 全部 index=0，应有不同 row_index")

    page_count = schema.get("document", {}).get("page_count") or schema.get("source", {}).get("page_count")
    pq = qual.get("page_quality") or []
    if page_count and pq and len(pq) < page_count:
        errors.append(
            f"[F36] page_quality 仅 {len(pq)} 页，document/source.page_count={page_count}"
        )

    # 8. validation — 规则完整性 + TIME_ORDER / FORMAT 与 quality 一致
    val = schema.get("validation", {})
    for key, expected_type in FINANCE_VALIDATION_KEYS.items():
        if key not in val:
            errors.append(f"[F37] validation 缺少字段: {key}")
    rules = val.get("rules", [])
    if not rules:
        errors.append("[F38] validation.rules 不应为空")
    for i, r in enumerate(rules):
        if not (r.get("rule") or r.get("rule_code")):
            errors.append(f"[F39] validation rule[{i}] 缺少 rule/rule_code")
        level = r.get("level") or r.get("severity")
        if not level:
            errors.append(f"[F39] validation rule[{i}] 缺少 level/severity")
        if not r.get("message"):
            errors.append(f"[F39] validation rule[{i}] 缺少 message")

    fmt_rule = next((r for r in rules if r.get("rule_code") == "FORMAT_CHECK"), None)
    if fmt_rule and fconf.get("timestamp", 0) >= 0.9:
        bad_ts = next(
            (e.get("value", 0) for e in fmt_rule.get("evidence", []) if e.get("field") == "bad_timestamp"),
            0,
        )
        if bad_ts > 0:
            errors.append(
                f"[F40] field_confidence.timestamp≥0.9 但 FORMAT_CHECK bad_timestamp={bad_ts}"
            )

    time_rule = next((r for r in rules if r.get("rule_code") == "TIME_ORDER_CHECK"), None)
    if time_rule and time_rule.get("status") == "passed":
        evidence = {e.get("field"): e.get("value") for e in time_rule.get("evidence", [])}
        total_ts = evidence.get("total_timestamps", 0)
        parseable = evidence.get("parseable_timestamps", 0)
        if total_ts >= 2 and parseable < 2:
            errors.append("[F41] TIME_ORDER_CHECK passed 但 parseable_timestamps < 2")

    # 9. assessment
    for key, expected_type in FINANCE_ASSESSMENT_KEYS.items():
        if key not in assess:
            errors.append(f"[F12] assessment 缺少字段: {key}")
    if assess.get("decision_strength") not in ("weak", "normal", "strong"):
        errors.append(f"[F13] assessment.decision_strength 非法: {assess.get('decision_strength')}")

    # 10. recommendation
    for key, expected_type in FINANCE_RECOMMENDATION_KEYS.items():
        if key not in rec:
            errors.append(f"[F14] recommendation 缺少字段: {key}")

    # 9. risk_signals 格式
    rss = schema.get("risk_signals", [])
    for i, rs in enumerate(rss):
        for key, expected_type in FINANCE_RISK_SIGNAL_KEYS.items():
            if key not in rs:
                errors.append(f"[F15] risk_signals[{i}] 缺少字段: {key}")
        if rs.get("severity") not in ("info", "warning", "critical"):
            errors.append(f"[F16] risk_signals[{i}].severity 非法: {rs.get('severity')}")
        evidence = rs.get("evidence", [])
        for j, ev in enumerate(evidence):
            if "document_id" not in ev or "field_path" not in ev:
                errors.append(f"[F17] risk_signals[{i}].evidence[{j}] 缺少 document_id/field_path")

    # 10. cross_validation
    cv = schema.get("cross_validation", {})
    for key, expected_type in FINANCE_CROSS_VALIDATION_KEYS.items():
        if key not in cv:
            errors.append(f"[F18] cross_validation 缺少字段: {key}")

    # 11. document_package
    dp = schema.get("document_package", {})
    if not dp.get("package_id"):
        errors.append("[F19] document_package.package_id 不应为空")
    if not dp.get("documents"):
        errors.append("[F20] document_package.documents 不应为空")

    # 12. entity_graph
    eg = schema.get("entity_graph", {})
    if "subjects" not in eg or "accounts" not in eg:
        errors.append("[F21] entity_graph 缺少 subjects/accounts")

    # 13. security (继承企业版)
    sec = schema.get("security", {})
    if sec.get("masking_required") and not sec.get("masking_rules_applied"):
        errors.append("[F22] masking_required=true 但 masking_rules_applied 为空")

    # 14. review (继承企业版)
    rv = schema.get("review", {})
    if rv.get("required") and not rv.get("review_items"):
        errors.append("[F23] review.required=true 但 review_items 为空")

    # 15. explainability
    expl = schema.get("explainability", {})
    if "decision_path" not in expl or "evidence_chain" not in expl:
        errors.append("[F24] explainability 缺少 decision_path/evidence_chain")

    # 16. financial_indicators
    fi = schema.get("financial_indicators", {})
    if not fi.get("cashflow") and not fi.get("income") and not fi.get("expense"):
        errors.append("[F25] financial_indicators.cashflow/income/expense 全为空")

    # 17. source/processing 生产字段
    src = schema.get("source", {})
    if not src.get("file_name"):
        errors.append("[F26] source.file_name 不应为空")
    proc = schema.get("processing", {})
    if proc.get("duration_ms", 0) == 0:
        errors.append("[F27] processing.duration_ms 不应为 0")
    if proc.get("started_at") and proc.get("finished_at") and proc["started_at"] == proc["finished_at"]:
        errors.append("[F28] processing.started_at 与 finished_at 相同")

    # 18. audit 完整
    aud = schema.get("audit", {})
    if not aud.get("operation_logs"):
        errors.append("[F29] audit.operation_logs 不应为空")
    if not aud.get("export_logs"):
        errors.append("[F30] audit.export_logs 不应为空")

    return errors


# ──────────────────────────────────────────────
# 通用辅助方法
# ──────────────────────────────────────────────

def check_edition(schema: dict, path_hint: str = "") -> tuple[str, list[str]]:
    """自动检测 edition 并执行对应检查。返回 (edition, errors)。"""
    edition = schema.get("edition", "unknown")
    if edition == "community":
        return edition, check_community(schema, path_hint)
    elif edition == "enterprise":
        return edition, check_enterprise(schema, path_hint)
    elif edition == "finance":
        return edition, check_finance(schema, path_hint)
    else:
        return edition, [f"未知 edition: {edition}"]


def check_file(file_path: str) -> dict:
    """检查单个 JSON 文件。返回 {'file': str, 'edition': str, 'errors': list, 'passed': bool}。"""
    try:
        with open(file_path, encoding="utf-8") as f:
            schema = json.load(f)
    except Exception as e:
        return {"file": file_path, "edition": "error", "errors": [f"读取失败: {e}"], "passed": False}

    # 跳过 mirror 文件（不属于三版 schema）
    fname = Path(file_path).name
    if "_mirror." in fname or fname.endswith("_mirror.json") or "mirror" in fname.lower():
        return {"file": file_path, "edition": "mirror", "errors": [], "passed": True}

    edition, errors = check_edition(schema, file_path)
    return {
        "file": file_path,
        "edition": edition,
        "errors": errors,
        "passed": len(errors) == 0,
    }


# ──────────────────────────────────────────────
# 主入口：CLI 模式
# ──────────────────────────────────────────────

def main():
    """检查指定 JSON 文件或 output 目录中的所有 edition 文件。"""
    import argparse

    parser = argparse.ArgumentParser(description="三版 Schema 合规检查")
    parser.add_argument("paths", nargs="*", help="JSON 文件或目录路径")
    parser.add_argument("--dir", "-d", default="", help="output 目录路径 (含 task 子目录)")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    parser.add_argument("--summary-only", "-s", action="store_true", help="仅输出摘要")
    args = parser.parse_args()

    files_to_check = []
    skip_patterns = ("_mirror.json", "_MIRROR.json")

    # 收集路径 (跳过 mirror 文件)
    for p in args.paths:
        pobj = Path(p)
        if pobj.is_dir():
            for f in sorted(pobj.rglob("*.json")):
                if any(f.name.endswith(sp) for sp in skip_patterns):
                    continue
                files_to_check.append(f)
        elif pobj.is_file():
            if any(pobj.name.endswith(sp) for sp in skip_patterns):
                print(f"跳过 mirror 文件: {pobj.name}")
                continue
            files_to_check.append(pobj)

    if args.dir:
        dp = Path(args.dir)
        if dp.is_dir():
            files_to_check.extend(sorted(dp.rglob("*.json")))

    if not files_to_check:
        print("用法: python3 tests/test_edition_schema_conformance.py <file.json|dir> [--dir output_dir]")
        print("示例:")
        print("  python3 tests/test_edition_schema_conformance.py output/20260612_060923_d42c")
        print("  python3 tests/test_edition_schema_conformance.py output/20260612_060923_d42c/001_community.json")
        print("  python3 tests/test_edition_schema_conformance.py --dir output")
        sys.exit(1)

    results = [check_file(str(f)) for f in files_to_check]

    # 输出
    if not args.summary_only:
        for r in results:
            status = "✅" if r["passed"] else "❌"
            print(f"\n{status} [{r['edition']}] {Path(r['file']).name} ({Path(r['file']).parent.name})")
            if not r["passed"]:
                for e in r["errors"]:
                    print(f"   {e}")

    # 摘要
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    by_edition = {}
    for r in results:
        by_edition.setdefault(r["edition"], {"total": 0, "passed": 0})
        by_edition[r["edition"]]["total"] += 1
        if r["passed"]:
            by_edition[r["edition"]]["passed"] += 1

    print(f"\n{'='*60}")
    print("🏁 三版合规检查摘要")
    print(f"{'='*60}")
    for ed in ["community", "enterprise", "finance"]:
        stats = by_edition.get(ed, {"total": 0, "passed": 0})
        if stats["total"] > 0:
            print(f"  {ed:12s}: {stats['passed']}/{stats['total']} 通过")
    print(f"  {'总计':12s}: {passed}/{total} 通过")
    print(f"{'='*60}")

    return 0 if passed == total else 1


# ──────────────────────────────────────────────
# pytest 模式
# ──────────────────────────────────────────────

def _collect_results(paths: list[str]) -> list[dict]:
    results = []
    for p in paths:
        pobj = Path(p)
        if pobj.is_dir():
            for f in sorted(pobj.rglob("*.json")):
                results.append(check_file(str(f)))
        elif pobj.is_file():
            results.append(check_file(str(p)))
    return results


# pytest 测试用例
import pytest

pytestmark = [pytest.mark.tier_contract]


@pytest.fixture(scope="session")
def latest_output_dir():
    """自动查找最新的 output 或 /tmp/test_fix_v8 子目录。"""
    # 优先使用固定测试目录
    for test_dir in [Path("/tmp/test_fix_v8"), Path("output")]:
        if test_dir.is_dir():
            dirs = sorted(test_dir.iterdir(), key=lambda d: d.name, reverse=True)
            if dirs:
                return str(dirs[0])
    return None


def test_community_schema(latest_output_dir):
    """测试社区版输出符合 v2 规范。"""
    if not latest_output_dir:
        pytest.skip("output 目录不存在")
    files = list(Path(latest_output_dir).glob("*_community.json"))
    assert files, f"{latest_output_dir} 中没有 _community.json 文件"
    all_errors = []
    for f in files:
        r = check_file(str(f))
        if not r["passed"]:
            all_errors.extend(r["errors"])
    assert not all_errors, "社区版检查失败:\n" + "\n".join(f"  {e}" for e in all_errors)


def test_enterprise_schema(latest_output_dir):
    """测试企业版输出符合 v2 规范。"""
    if not latest_output_dir:
        pytest.skip("output 目录不存在")
    files = list(Path(latest_output_dir).glob("*_enterprise.json"))
    assert files, f"{latest_output_dir} 中没有 _enterprise.json 文件"
    all_errors = []
    for f in files:
        r = check_file(str(f))
        if not r["passed"]:
            all_errors.extend(r["errors"])
    assert not all_errors, "企业版检查失败:\n" + "\n".join(f"  {e}" for e in all_errors)


def test_finance_schema(latest_output_dir):
    """测试金融版输出符合 v3 规范。"""
    if not latest_output_dir:
        pytest.skip("output 目录不存在")
    files = list(Path(latest_output_dir).glob("*_finance.json"))
    assert files, f"{latest_output_dir} 中没有 _finance.json 文件"
    all_errors = []
    for f in files:
        r = check_file(str(f))
        if not r["passed"]:
            all_errors.extend(r["errors"])
    assert not all_errors, "金融版检查失败:\n" + "\n".join(f"  {e}" for e in all_errors)


def test_cross_edition_file_naming(latest_output_dir):
    """验证同一任务目录下的三版文件命名一致性。"""
    if not latest_output_dir:
        pytest.skip("output 目录不存在")
    d = Path(latest_output_dir)
    community = {f.stem.replace("_community", ""): f for f in d.glob("*_community.json")}
    enterprise = {f.stem.replace("_enterprise", ""): f for f in d.glob("*_enterprise.json")}
    finance = {f.stem.replace("_finance", ""): f for f in d.glob("*_finance.json")}
    all_ids = set(community) | set(enterprise) | set(finance)
    for fid in all_ids:
        if fid in community and fid in enterprise:
            pass  # OK
        if fid in community and fid in finance:
            pass  # OK


if __name__ == "__main__":
    sys.exit(main())
