"""
Scene detection middleware (Scene Detector)
================================

三 layer递进式场景Detect:
    Tier 1 (关键字规则):  速度快，override常见场景
    Tier 2 (Table header特征):    结构化特征Analyze
    Tier 3 (LLM 裁决):    仅在前两 layerConfidence低时Trigger

supports的场景:
    - bank_statement:    Bank statement
    - invoice:           Invoice
    - tax_report:        纳税/完税证明
    - financial_report:  财务报告
    - credit_report:     信用报告
    - contract:          Contract
    - generic:           通用/Unknown
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ..base import BaseMiddleware
from ...models.enhanced import EnhancedResult

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 场景关键字库
# ═══════════════════════════════════════════════════════════════════════════════

SCENE_KEYWORDS: Dict[str, List[List[str]]] = {
    "bank_statement": [
        # 每组关键字必须all命中才算Match
        ["交易明细"],
        ["银行", "流水"],
        ["Account number", "交易"],
        ["Transaction", "Balance"],
        ["Statement", "Account"],
    ],
    "invoice": [
        ["Invoice number"],
        ["增值税", "Invoice"],
        ["Invoice", "Tax"],
    ],
    "financial_report": [
        ["审计报告"],
        ["资产负债 table"],
        ["利润 table"],
        ["Annual Report"],
    ],
    "credit_report": [
        ["Credit report"],
        ["信用报告"],
        ["Credit Report"],
    ],
    "contract": [
        ["Contract number"],
        ["Party A", "Party B"],
        ["Contract No"],
    ],
    "tax_report": [
        ["纳税证明"],
        ["税收完税证明"],
        ["完税证明"],
        ["税务", "完税"],
    ],
}

# Table header特征: 如果Table的Table headercontains这些列名Composition，可以推断场景
HEADER_FEATURES: Dict[str, List[Set[str]]] = {
    "bank_statement": [
        {"Transaction date", "Amount"},
        {"交易日", "Balance"},
        {"Date", "Amount", "Balance"},
        {"交易时间", "Transaction amount"},
        {"Transaction date", "Transaction amount", "AccountBalance"},
        {"Abstract/Summary", "Amount", "Balance"},
    ],
    "invoice": [
        {"品名", "数量", "单价", "Amount"},
        {"货物", "Tax rate", "Tax amount"},
    ],
    "tax_report": [
        {"税款", "税种", "入库Date"},
        {"纳税Amount", "完税"},
        {"税务机关", "完税证明"},
    ],
}


class SceneDetector(BaseMiddleware):
    """
    Scene detection middleware。

    Update ``EnhancedResult.scene`` Field。
    """

    def process(self, result: EnhancedResult) -> EnhancedResult:
        """Execute三 layer递进式场景Detect。"""
        if result.base_result is None:
            result.scene = "generic"
            return result

        full_text = result.base_result.full_text
        entities = result.base_result.entities
        table_blocks = result.base_result.table_blocks

        # ── Tier 1: 关键字规则 ──
        scene, confidence = self._tier1_keyword(full_text)
        if confidence >= 0.8:
            result.scene = scene
            result.record_mutation(
                middleware_name=self.name,
                target_block_id="document",
                field_changed="scene",
                old_value="unknown",
                new_value=scene,
                confidence=confidence,
                reason=f"Tier1 keyword match",
            )
            logger.info(f"[SceneDetector] Tier1 → {scene} (conf={confidence:.2f})")
            return result

        # ── Tier 2: Table header特征 ──
        scene_t2, conf_t2 = self._tier2_header_features(table_blocks)
        if conf_t2 > confidence:
            scene, confidence = scene_t2, conf_t2

        # 综合 Tier 1 + Tier 2 的 entity 信号
        scene_entity, conf_entity = self._detect_from_entities(entities)
        if conf_entity > confidence:
            scene, confidence = scene_entity, conf_entity

        # ── 视觉特征加权: BoldTitle含Keywords = 强信号 ──
        visual_boost = self._visual_feature_boost(result.base_result)
        if visual_boost[1] > 0 and visual_boost[0] == scene:
            confidence = min(0.95, confidence + visual_boost[1])
        elif visual_boost[1] > confidence:
            scene, confidence = visual_boost[0], visual_boost[1]

        if confidence >= 0.6:
            result.scene = scene
            result.record_mutation(
                middleware_name=self.name,
                target_block_id="document",
                field_changed="scene",
                old_value="unknown",
                new_value=scene,
                confidence=confidence,
                reason=f"Tier2 feature+visual match",
            )
            logger.info(f"[SceneDetector] Tier2 → {scene} (conf={confidence:.2f})")
            return result

        # ── Tier 3: LLM 裁决 (仅在Low confidence时) ──
        scene_llm, conf_llm = self._tier3_llm(full_text[:2000])
        if conf_llm > confidence:
            scene, confidence = scene_llm, conf_llm

        result.scene = scene if confidence >= 0.3 else "generic"
        result.record_mutation(
            middleware_name=self.name,
            target_block_id="document",
            field_changed="scene",
            old_value="unknown",
            new_value=result.scene,
            confidence=confidence,
            reason=f"Tier3 LLM" if conf_llm > 0 else "low confidence fallback",
        )
        logger.info(f"[SceneDetector] Final → {result.scene} (conf={confidence:.2f})")
        return result

    # ── Tier 1: 关键字规则 ──

    def _tier1_keyword(self, text: str) -> Tuple[str, float]:
        """关键字组Match — 任意一组all命中即判定。"""
        if not text:
            return "generic", 0.0

        best_scene = "generic"
        best_conf = 0.0

        for scene, keyword_groups in SCENE_KEYWORDS.items():
            for group in keyword_groups:
                if all(kw in text for kw in group):
                    # 多组命中 → Confidence更高
                    conf = min(0.9, 0.7 + 0.1 * len(group))
                    if conf > best_conf:
                        best_scene = scene
                        best_conf = conf

        return best_scene, best_conf

    # ── Tier 2: Table header特征 ──

    def _tier2_header_features(self, table_blocks) -> Tuple[str, float]:
        """AnalyzeTableTable header列名推断场景。"""
        if not table_blocks:
            return "generic", 0.0

        for block in table_blocks:
            raw = block.raw_content
            if not isinstance(raw, list) or not raw:
                continue

            # 获取Table header (第一行)
            header = raw[0] if raw else []
            header_set = {str(h).strip() for h in header if h}

            for scene, feature_groups in HEADER_FEATURES.items():
                for required in feature_groups:
                    # 模糊子串Match
                    matched = 0
                    for req_kw in required:
                        for h in header_set:
                            if req_kw in h or h in req_kw:
                                matched += 1
                                break
                    if matched >= len(required) * 0.6:
                        conf = min(0.85, 0.5 + 0.15 * matched)
                        return scene, conf

        return "generic", 0.0

    # ── 视觉特征加权 ──

    def _visual_feature_boost(self, base_result) -> Tuple[str, float]:
        """
        利用 Style 视觉特征增强场景Detect。

        人类看Document时，大Font sizeBoldTitle是最强信号。
        如果Title含"银行"、Bold、Font size>14 → 几乎确定是Bank statement。
        """
        if base_result is None:
            return "generic", 0.0

        boost_scene = "generic"
        boost_conf = 0.0

        # 视觉KeywordsMap
        visual_keywords = {
            "bank_statement": ["银行", "Bank", "流水", "Statement", "交易明细"],
            "invoice": ["Invoice", "Invoice", "增值税"],
            "financial_report": ["审计", "报 table", "Annual Report"],
            "credit_report": ["征信", "信用报告"],
            "contract": ["Contract", "Contract", "Protocol"],
        }

        for block in base_result.all_blocks:
            if block.block_type not in ("title", "text"):
                continue
            for span in block.spans:
                style = span.style
                text = span.text

                # Bold + 大Font size → 强信号
                is_prominent = (
                    (style.is_bold and style.font_size >= 12)
                    or style.font_size >= 16
                )
                if not is_prominent:
                    continue

                for scene, keywords in visual_keywords.items():
                    for kw in keywords:
                        if kw in text:
                            conf = 0.6
                            if style.is_bold and style.font_size >= 14:
                                conf = 0.75
                            if conf > boost_conf:
                                boost_scene = scene
                                boost_conf = conf

        return boost_scene, boost_conf

    # ── Entity 信号 ──

    def _detect_from_entities(self, entities: Dict[str, str]) -> Tuple[str, float]:
        """从 key_value 实体推断场景。"""
        if not entities:
            return "generic", 0.0

        keys = set(entities.keys())

        # Bank statement特征 key
        bank_keys = {"Account name", "Account number", "Account name", "Card number", "Bank name", "Query period",
                      "Account name称", "Customer name", "打印Period"}
        matched = len(keys & bank_keys)
        if matched >= 2:
            return "bank_statement", min(0.85, 0.5 + 0.15 * matched)

        # Invoice特征 key
        invoice_keys = {"Invoice代码", "Invoice number", "Buyer", "Seller", "Tax amount"}
        matched = len(keys & invoice_keys)
        if matched >= 2:
            return "invoice", min(0.85, 0.5 + 0.15 * matched)

        return "generic", 0.0

    # ── Tier 3: LLM 裁决 ──

    def _tier3_llm(self, text_snippet: str) -> Tuple[str, float]:
        """
        LLM 场景判断 — 仅在 Tier 1+2 都Low confidence时call。

        Optimize: using精简 Prompt，只发送前 2000 字符，控制成本。
        """
        if not self.config.get("enable_llm", False):
            return "generic", 0.0

        try:
            # retain LLM callInterface，但Default不Enable
            # 如需Enable，Configuration enable_llm=True 并注入 LLM client
            logger.debug("[SceneDetector] Tier3 LLM skipped (not enabled)")
            return "generic", 0.0
        except Exception as e:
            logger.debug(f"[SceneDetector] Tier3 LLM error: {e}")
            return "generic", 0.0
