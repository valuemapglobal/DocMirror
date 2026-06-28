# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Document type candidates — multi-source evidence collectors.

Purpose: Gathers keyword, header, entity, plugin, and visual classification
hypotheses with scores for resolver fusion.

Main components: ``collect_keyword_candidates``, ``collect_header_candidates``,
``collect_entity_candidates``.

Upstream: Full text, headers, plugin registry, page renders.

Downstream: ``DocumentTypeResolver.resolve``.
"""

from __future__ import annotations

import uuid
from typing import Any

from docmirror.configs.scene.loader import get_plugin_scene_keywords, get_scene_specs
from docmirror.framework.extension_points import get_plugin_candidate_provider
from docmirror.models.entities.hypothesis import ParseHypothesis
from docmirror.models.entities.parse_result import ParseResult

EVIDENCE_KEYWORDS = {
    scene: list(getattr(spec, "keywords", []) or [])
    for scene, spec in (get_scene_specs() or {}).items()
}

_HEADER_SIGS: dict[str, list[set[str]]] = {
    "bank_statement": [
        {"交易时间", "金额", "余额", "对方户名", "摘要"},
        {"交易日期", "摘要", "存入", "支出", "余额"},
        {"DATE", "DESCRIPTION", "DEBITS", "CREDITS", "BALANCE"},
        {"记账日期", "交易类型", "对方账号", "对方户名", "金额"},
    ],
    "credit_report": [
        {"报告编号", "查询时间", "被查询者", "证件类型", "证件号码"},
        {"被查询者姓名", "被查询者证件号码"},
        {"信贷记录", "非信贷交易记录", "公共记录"},
        {"账户数", "余额", "还款情况"},
    ],
    "invoice_vat": [
        {"发票代码", "发票号码", "开票日期", "购方名称", "销方名称"},
        {"货物或应税劳务名称", "规格型号", "数量", "单价", "金额"},
    ],
    "wechat_payment": [
        {"交易单号", "交易时间", "交易类型", "收/支", "金额"},
        {"交易单号", "交易时间", "收/支/其他", "金额(元)"},
        {"交易单号", "对方", "金额", "时间"},
    ],
    "alipay_payment": [
        {"交易记录", "交易号", "时间", "金额", "对方"},
        {"交易号", "商品说明", "时间", "金额", "状态"},
    ],
    "insurance_policy": [
        {"保险单号", "被保险人", "保险人", "保险期间", "保费"},
        {"保单号", "投保人", "被保险人", "保险金额"},
        {"Policy No", "Insured", "Premium", "Period"},
    ],
    "business_license": [
        {"统一社会信用代码", "名称", "类型", "住所", "法定代表人"},
        {"注册资本", "成立日期", "营业期限", "经营范围"},
    ],
    "household_register": [
        {"户号", "户主姓名", "与户主关系", "姓名", "性别"},
        {"户号", "姓名", "身份证号", "住址"},
    ],
    "id_card": [
        {"姓名", "性别", "民族", "出生", "住址"},
        {"公民身份号码", "Name", "Sex", "Nationality"},
    ],
}


def _hyp(
    scene: str,
    confidence: float,
    method: str,
    *,
    evidence_ids: list[str] | None = None,
) -> ParseHypothesis:
    return ParseHypothesis(
        id=f"doctype_{scene}_{uuid.uuid4().hex[:6]}",
        kind="document_type",
        payload={"document_type": scene},
        confidence=confidence,
        method=method,
        evidence_ids=evidence_ids or [],
    )


def collect_keyword_candidates(text: str) -> list[ParseHypothesis]:
    if not text:
        return []

    candidates: list[ParseHypothesis] = []

    if "微信支付交易明细证明" in text:
        candidates.append(_hyp("wechat_payment", 0.92, "tier1_keyword"))
    if "财付通" in text and "交易明细" in text:
        candidates.append(_hyp("wechat_payment", 0.88, "tier1_keyword"))

    for marker in ("个人信用报告", "企业信用报告", "征信报告"):
        if marker in text:
            candidates.append(_hyp("credit_report", 0.93, "tier1_keyword"))
            break

    plugin_keywords = get_plugin_scene_keywords()
    all_scenes = set(EVIDENCE_KEYWORDS.keys()) | set(plugin_keywords.keys())

    for scene in all_scenes:
        keyword_groups = EVIDENCE_KEYWORDS.get(scene, [])
        dynamic_kws = plugin_keywords.get(scene, [])
        groups = keyword_groups + [[kw] for kw in dynamic_kws]
        for group in groups:
            if all(kw in text for kw in group):
                conf = round(min(0.9, 0.7 + 0.1 * len(group)), 2)
                candidates.append(_hyp(scene, conf, "tier1_keyword"))

    return candidates


def collect_header_candidates(table_blocks: list[Any]) -> list[ParseHypothesis]:
    candidates: list[ParseHypothesis] = []
    if not table_blocks:
        return candidates

    for table in table_blocks:
        if not table.headers:
            continue
        header_set = {str(h).strip() for h in table.headers if h}
        for scene, feature_groups in _header_sigs.items():
            for required in feature_groups:
                matched = 0
                for req_kw in required:
                    for h in header_set:
                        if req_kw in h or h in req_kw:
                            matched += 1
                            break
                if matched >= len(required) * 0.6:
                    conf = min(0.85, 0.5 + 0.15 * matched)
                    candidates.append(_hyp(scene, conf, "tier2_header"))
    return candidates


def collect_entity_candidates(entities: dict[str, str]) -> list[ParseHypothesis]:
    if not entities:
        return []
    keys = set(entities.keys())
    candidates: list[ParseHypothesis] = []

    bank_keys = {
        "Account name",
        "Account number",
        "Card number",
        "Bank name",
        "Query period",
        "Account name称",
        "Customer name",
        "打印Period",
    }
    matched = len(keys & bank_keys)
    if matched >= 2:
        candidates.append(_hyp("bank_statement", min(0.85, 0.5 + 0.15 * matched), "entity_keys"))

    invoice_keys = {"Invoice代码", "Invoice number", "Buyer", "Seller", "Tax amount"}
    matched = len(keys & invoice_keys)
    if matched >= 2:
        candidates.append(_hyp("invoice", min(0.85, 0.5 + 0.15 * matched), "entity_keys"))

    return candidates


def collect_plugin_candidates(text: str, parse_result: ParseResult | None = None) -> list[ParseHypothesis]:
    provider = get_plugin_candidate_provider()
    if provider is None:
        return []
    try:
        return provider(text, parse_result)
    except Exception:
        return []


def collect_visual_candidates(result: ParseResult) -> list[ParseHypothesis]:
    candidates: list[ParseHypothesis] = []
    visual_keywords = {
        "bank_statement": ["银行", "Bank", "流水", "Statement", "交易明细"],
        "invoice": ["Invoice", "增值税"],
        "financial_report": ["审计", "Annual Report"],
        "credit_report": ["征信", "信用报告"],
        "contract": ["Contract", "Protocol"],
        "wechat_payment": ["微信支付", "财付通"],
    }
    for scene, kws in get_plugin_scene_keywords().items():
        visual_keywords.setdefault(scene, []).extend(kws)

    for page in result.pages:
        for text_block in page.texts:
            if text_block.level.value not in ("title", "h1", "h2"):
                continue
            content = text_block.content or ""
            for scene, keywords in visual_keywords.items():
                for kw in keywords:
                    if kw in content:
                        conf = 0.75 if text_block.level.value in ("title", "h1") else 0.65
                        candidates.append(_hyp(scene, conf, "visual_heading"))
                        break
    return candidates


def dedupe_candidates(candidates: list[ParseHypothesis]) -> list[ParseHypothesis]:
    """Keep highest-confidence hypothesis per document_type."""
    best: dict[str, ParseHypothesis] = {}
    for c in candidates:
        dt = c.payload.get("document_type", "unknown")
        prev = best.get(dt)
        if prev is None or c.confidence > prev.confidence:
            best[dt] = c
    return list(best.values())


def collect_document_type_candidates(
    *,
    full_text: str,
    table_blocks: list[Any],
    entities: dict[str, str],
    result: ParseResult,
) -> list[ParseHypothesis]:
    """Aggregate all document-type hypotheses before resolver adjudication."""
    out: list[ParseHypothesis] = []
    out.extend(collect_keyword_candidates(full_text))
    out.extend(collect_header_candidates(table_blocks))
    out.extend(collect_entity_candidates(entities))
    out.extend(collect_plugin_candidates(full_text, result))
    out.extend(collect_visual_candidates(result))
    return dedupe_candidates(out)
