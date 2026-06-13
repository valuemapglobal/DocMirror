# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Evidence Engine (EvidenceEngine)
==================================

Multi-dimensional evidence-based document classification middleware.

Replaces SceneDetector with a more robust, first-principles approach:
    - Collects evidence from multiple sources (keyword, header, entity, visual, metadata)
    - Each evidence is a weighted signal (+1 for support, -1 for exclusion)
    - Final classification is softmax fusion across all evidence sources
    - Exclusion is a hard veto (if exclude keyword matches, category is eliminated)

Architecture:
    EvidenceEngine collects all evidence → fuses with softmax → outputs verdict

Usage::
    from docmirror.core.classification.evidence_engine import EvidenceEngine
"""

from __future__ import annotations
from pathlib import Path
import yaml

import logging
from typing import Any, Dict, List, Optional, Tuple

from ...models.entities.parse_result import ParseResult
from ...middlewares.base import BaseMiddleware
from docmirror.core.debug.artifact import is_debug_mode

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Evidence Data Structure
# ═══════════════════════════════════════════════════════════════════════════════


class Evidence:
    """A single evidence signal for document classification."""

    __slots__ = ("source", "category", "weight", "direction", "detail")

    def __init__(
        self,
        source: str,
        category: str,
        weight: float,
        direction: int,
        detail: str,
    ):
        self.source = source       # "keyword" / "header" / "entity" / "visual" / "metadata"
        self.category = category   # target category name
        self.weight = weight       # evidence strength 0.0-1.0 (or penalty magnitude for -1)
        self.direction = direction # +1 support, -1 exclusion
        self.detail = detail       # human-readable explanation

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "category": self.category,
            "weight": round(self.weight, 3),
            "direction": self.direction,
            "detail": self.detail,
        }

    def __repr__(self) -> str:
        return (
            f"Evidence(source={self.source}, category={self.category}, "
            f"weight={self.weight:.3f}, direction={'+' if self.direction == 1 else '-'})"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Keyword Data Loading
# ═══════════════════════════════════════════════════════════════════════════════

_SCENE_KEYWORDS: dict[str, list[str]] | None = None
_SCENE_EXCLUDE: dict[str, list[str]] | None = None


def _load_scene_keywords() -> None:
    """Load all scene keywords (include + exclude) from YAML config."""
    global _SCENE_KEYWORDS, _SCENE_EXCLUDE
    if _SCENE_KEYWORDS is not None:
        return

    _path = Path(__file__).resolve().parent.parent.parent / "configs" / "scene_keywords.yaml"
    _includes: dict[str, list[str]] = {}
    _excludes: dict[str, list[str]] = {}
    try:
        if _path.exists():
            with open(_path) as f:
                raw = yaml.safe_load(f).get("scene_keywords", {})
            for category, content in raw.items():
                if isinstance(content, dict):
                    inc = content.get("include", [])
                    exc = content.get("exclude", [])
                    if inc:
                        _includes[category] = [kw for kw in inc if isinstance(kw, str) and len(kw) >= 2]
                    if exc:
                        _excludes[category] = [kw for kw in exc if isinstance(kw, str) and len(kw) >= 2]
                elif isinstance(content, list):
                    _includes[category] = [kw for kw in content if isinstance(kw, str) and len(kw) >= 2]
    except Exception as exc:
        logger.error(f"[EvidenceEngine] Failed to load scene keywords: {exc}")

    _SCENE_KEYWORDS = _includes
    _SCENE_EXCLUDE = _excludes
    logger.info(f"[EvidenceEngine] Loaded {len(_includes)} categories, {len(_excludes)} with exclude rules")


_load_scene_keywords()

# Precomputed keyword uniqueness weights: shared across all EvidenceEngine instances
_KW_UNIQUENESS: dict[str, float] | None = None


def _compute_uniqueness() -> None:
    """Compute how unique each keyword is across categories."""
    global _KW_UNIQUENESS
    if _KW_UNIQUENESS is not None:
        return
    _kws = _SCENE_KEYWORDS or {}
    cnt: dict[str, int] = {}
    for _kws_list in _kws.values():
        for _kw in _kws_list:
            cnt[_kw] = cnt.get(_kw, 0) + 1
    _KW_UNIQUENESS = {_kw: 1.0 / max(_cnt, 1) for _kw, _cnt in cnt.items()}


_compute_uniqueness()


# ═══════════════════════════════════════════════════════════════════════════════
# EvidenceEngine Middleware
# ═══════════════════════════════════════════════════════════════════════════════




class EvidenceEngine(BaseMiddleware):
    """
    Multi-dimensional evidence-based document classification.

    Replaces SceneDetector. Collects evidence from:
        - keyword matching (include + exclude)
        - table header structure
        - entity field presence
        - visual/typographic features
        - metadata (page count, file type)

    Evidence is fused via softmax-based confidence calculation.
    """

    def process(self, result: ParseResult) -> ParseResult:
        """Collect evidence, fuse, and set document_type."""
        all_evidence: list[Evidence] = []

        # Phase 1: Collect evidence from all sources
        all_evidence.extend(self._keyword_evidence(result.full_text))
        all_evidence.extend(self._header_evidence(result.all_tables()))
        all_evidence.extend(self._entity_evidence(result.kv_entities))
        all_evidence.extend(self._visual_evidence(result.pages))

        # Phase 2: Fuse evidence
        verdict, confidence, fused_evidence = self._fuse_evidence(all_evidence)

        # Phase 3: Apply verdict
        doc_type = verdict if confidence >= 0.3 else "generic"
        result.entities.document_type = doc_type

        # Phase 3b: Refine layout profile hint for ledger archetypes (does not re-extract)
        from docmirror.core.classification.scene_resolver import scene_to_layout_profile_id

        refined_profile = scene_to_layout_profile_id(doc_type)
        if refined_profile:
            ds = result.entities.domain_specific
            if not isinstance(ds, dict):
                ds = {}
            ds["document_scene_refined"] = doc_type
            ds["layout_profile_id_refined"] = refined_profile
            ds["layout_profile_refine_confidence"] = confidence
            result.entities.domain_specific = ds

        # Evidence log for debugging (mirror/API only when DOCMIRROR_DEBUG=1)
        if (
            is_debug_mode()
            and hasattr(result.entities, "domain_specific")
            and isinstance(result.entities.domain_specific, dict)
        ):
            result.entities.domain_specific["evidence_log"] = fused_evidence

        result.record_mutation(
            middleware_name=self.name,
            target_block_id="document",
            field_changed="scene",
            old_value=getattr(result.entities, 'document_type', "unknown"),
            new_value=doc_type,
            confidence=confidence,
            reason=f"evidence_fusion (best={verdict}, conf={confidence:.2f})",
        )

        logger.info(
            f"[EvidenceEngine] {doc_type} (conf={confidence:.2f}) | "
            f"{len(all_evidence)} evidence items"
        )
        return result

    # ─── Keyword Evidence (with exclusion veto) ───

    def _keyword_evidence(self, full_text: str) -> list[Evidence]:
        """Collect keyword-based evidence: include positive, exclude is veto."""
        if not full_text:
            return []

        evidence: list[Evidence] = []
        includes = _SCENE_KEYWORDS or {}
        excludes = _SCENE_EXCLUDE or {}

        if not includes:
            return []

        # Precompute uniqueness weights
        if not hasattr(self, '_kw_uniqueness'):
            self._kw_uniqueness = {}
            cnt_cache: dict[str, int] = {}
            for _scene, _kws in includes.items():
                for _kw in _kws:
                    cnt_cache[_kw] = cnt_cache.get(_kw, 0) + 1
            for _kw, _cnt in cnt_cache.items():
                self._kw_uniqueness[_kw] = 1.0 / max(_cnt, 1)

        # Include keyword scoring
        for scene, kws in includes.items():
            score = 0.0
            matched = []
            for kw in kws:
                if kw in full_text:
                    matched.append(kw)
                    uniqueness = self._kw_uniqueness.get(kw, 0.5)
                    lf = 3 if len(kw) >= 8 else (2 if len(kw) >= 5 else 1)
                    score += uniqueness * lf
            if score >= 0.5:
                evidence.append(Evidence(
                    source="keyword",
                    category=scene,
                    weight=min(score / 10.0, 0.95),
                    direction=1,
                    detail=f"include matches: {matched} (score={score:.1f})",
                ))

        # Exclusion (hard veto)
        for scene, kws in excludes.items():
            matched = [kw for kw in kws if kw in full_text]
            if matched:
                evidence.append(Evidence(
                    source="keyword_exclude",
                    category=scene,
                    weight=100.0,  # absolute veto
                    direction=-1,
                    detail=f"hard veto by exclusion: {matched}",
                ))

        return evidence

    # ─── Header Evidence ───

    def _header_evidence(self, table_blocks) -> list[Evidence]:
        """Match table headers against known column-name signatures."""
        if not table_blocks:
            return []

        # Structural column-header signatures (not data-driven — these are
        # layout features of specific document types, not keywords)
        _header_sigs: dict[str, list[set[str]]] = {
            "bank_statement": [
                {"\u4ea4\u6613\u65f6\u95f4", "\u91d1\u989d", "\u4f59\u989d", "\u5bf9\u65b9\u6237\u540d", "\u6458\u8981"},
                {"\u4ea4\u6613\u65e5\u671f", "\u6458\u8981", "\u5b58\u5165", "\u652f\u51fa", "\u4f59\u989d"},
                {"DATE", "DESCRIPTION", "DEBITS", "CREDITS", "BALANCE"},
                {"\u8bb0\u8d26\u65e5\u671f", "\u4ea4\u6613\u7c7b\u578b", "\u5bf9\u65b9\u8d26\u53f7", "\u5bf9\u65b9\u6237\u540d", "\u91d1\u989d"},
            ],
            "credit_report": [
                {"\u62a5\u544a\u7f16\u53f7", "\u67e5\u8be2\u65f6\u95f4", "\u88ab\u67e5\u8be2\u8005", "\u8bc1\u4ef6\u7c7b\u578b", "\u8bc1\u4ef6\u53f7\u7801"},
                {"\u88ab\u67e5\u8be2\u8005\u59d3\u540d", "\u88ab\u67e5\u8be2\u8005\u8bc1\u4ef6\u53f7\u7801"},
                {"\u8d37\u4fe1\u8bb0\u5f55", "\u975e\u4fe1\u8d37\u4ea4\u6613\u8bb0\u5f55", "\u516c\u5171\u8bb0\u5f55"},
                {"\u8d26\u6237\u6570", "\u4f59\u989d", "\u8fd8\u6b3e\u60c5\u51b5"},
            ],
            "invoice_vat": [
                {"\u53d1\u7968\u4ee3\u7801", "\u53d1\u7968\u53f7\u7801", "\u5f00\u7968\u65e5\u671f", "\u8d2d\u65b9\u540d\u79f0", "\u9500\u65b9\u540d\u79f0"},
                {"\u8d27\u7269\u6216\u5e94\u7a0e\u52b3\u52a1\u540d\u79f0", "\u89c4\u683c\u578b\u53f7", "\u6570\u91cf", "\u5355\u4ef7", "\u91d1\u989d"},
            ],
            "wechat_payment": [
                {"\u4ea4\u6613\u5355\u53f7", "\u4ea4\u6613\u65f6\u95f4", "\u4ea4\u6613\u7c7b\u578b", "\u6536/\u652f", "\u91d1\u989d"},
                {"\u4ea4\u6613\u5355\u53f7", "\u4ea4\u6613\u65f6\u95f4", "\u6536/\u652f/\u5176\u4ed6", "\u91d1\u989d(\u5143)"},
                {"\u4ea4\u6613\u5355\u53f7", "\u5bf9\u65b9", "\u91d1\u989d", "\u65f6\u95f4"},
            ],
            "alipay_payment": [
                {"\u4ea4\u6613\u8bb0\u5f55", "\u4ea4\u6613\u53f7", "\u65f6\u95f4", "\u91d1\u989d", "\u5bf9\u65b9"},
                {"\u4ea4\u6613\u53f7", "\u5546\u54c1\u8bf4\u660e", "\u65f6\u95f4", "\u91d1\u989d", "\u72b6\u6001"},
            ],
            "insurance_policy": [
                {"\u4fdd\u9669\u5355\u53f7", "\u88ab\u4fdd\u9669\u4eba", "\u4fdd\u9669\u4eba", "\u4fdd\u9669\u671f\u95f4", "\u4fdd\u8d39"},
                {"\u4fdd\u5355\u53f7", "\u6295\u4fdd\u4eba", "\u88ab\u4fdd\u9669\u4eba", "\u4fdd\u9669\u91d1\u989d"},
                {"Policy No", "Insured", "Premium", "Period"},
            ],
            "business_license": [
                {"\u7edf\u4e00\u793e\u4f1a\u4fe1\u7528\u4ee3\u7801", "\u540d\u79f0", "\u7c7b\u578b", "\u4f4f\u6240", "\u6cd5\u5b9a\u4ee3\u8868\u4eba"},
                {"\u6ce8\u518c\u8d44\u672c", "\u6210\u7acb\u65e5\u671f", "\u8425\u4e1a\u671f\u9650", "\u7ecf\u8425\u8303\u56f4"},
            ],
            "household_register": [
                {"\u6237\u53f7", "\u6237\u4e3b\u59d3\u540d", "\u4e0e\u6237\u4e3b\u5173\u7cfb", "\u59d3\u540d", "\u6027\u522b"},
                {"\u6237\u53f7", "\u59d3\u540d", "\u8eab\u4efd\u8bc1\u53f7", "\u4f4f\u5740"},
            ],
            "id_card": [
                {"\u59d3\u540d", "\u6027\u522b", "\u6c11\u65cf", "\u51fa\u751f", "\u4f4f\u5740"},
                {"\u516c\u6c11\u8eab\u4efd\u53f7\u7801", "Name", "Sex", "Nationality"},
            ],
        }

        evidence: list[Evidence] = []

        for scene, feature_groups in _header_sigs.items():
            for table in table_blocks:
                if not table.headers:
                    continue
                header_set = {str(h).strip() for h in table.headers if h}
                for required in feature_groups:
                    matched = 0
                    for req_kw in required:
                        for h in header_set:
                            if req_kw in h or h in req_kw:
                                matched += 1
                                break
                    if matched >= len(required) * 0.6:
                        conf = min(0.35, 0.15 + 0.04 * matched)
                        evidence.append(Evidence(
                            source="header",
                            category=scene,
                            weight=conf,
                            direction=1,
                            detail=f"matched {matched}/{len(required)} header columns",
                        ))
                        break  # one match per category is enough

        return evidence

    # ─── Entity Evidence ───

    def _entity_evidence(self, entities) -> list[Evidence]:
        """Use entity fields extracted by EntityExtractor to classify document type.

        Maps extracted entity keys to document categories via known patterns:
          - bank_name / Account name / Account number → bank_statement
          - invoice_code / invoice_number / buyer / seller → invoice_vat
          - subject_name / id_number / name / id_number → credit_report / id_card
        """
        if not entities:
            return []

        # Handle different entity access patterns
        if isinstance(entities, dict):
            keys = set(entities.keys())
        elif hasattr(entities, 'kv_entities') and entities.kv_entities:
            keys = set(entities.kv_entities.keys())
        else:
            return []

        # Build evidence per category based on known entity key signatures
        evidence: list[Evidence] = []

        # Bank statement: bank_name OR (Account name + Account number)
        if "bank_name" in keys:
            evidence.append(Evidence(
                source="entity", category="bank_statement",
                weight=0.15, direction=1,
                detail="entity has bank_name",
            ))
        bank_fields = {"Account name", "Account number", "bank_name", "Card number", "Query period"}
        bank_match = len(keys & bank_fields)
        if bank_match >= 2:
            evidence.append(Evidence(
                source="entity", category="bank_statement",
                weight=min(0.10 + 0.05 * bank_match, 0.25), direction=1,
                detail=f"bank entity fields: matched {bank_match}",
            ))

        # Invoice/增值税发票: contains invoice_code or invoice_number
        inv_fields = {"invoice_code", "invoice_number", "buyer", "seller",
                      "Invoice\u4ee3\u7801", "Invoice number", "Buyer", "Seller"}
        inv_match = len(keys & inv_fields)
        if inv_match >= 2:
            evidence.append(Evidence(
                source="entity", category="invoice_vat",
                weight=min(0.10 + 0.05 * inv_match, 0.25), direction=1,
                detail=f"invoice entity fields: matched {inv_match}",
            ))

        # Credit report / ID card: contains subject_name + id_number
        id_fields = {"name", "id_number", "subject_name",
                     "Name", "ID number", "\u516c\u6c11\u8eab\u4efd\u53f7\u7801",
                     "\u88ab\u67e5\u8be2\u8005"}
        id_match = len(keys & id_fields)
        if id_match >= 2:
            evidence.append(Evidence(
                source="entity", category="credit_report",
                weight=min(0.10 + 0.05 * id_match, 0.25), direction=1,
                detail=f"identity entity fields: matched {id_match}",
            ))

        return evidence
    def _visual_evidence(self, pages) -> list[Evidence]:
        """Use title/heading text to boost confidence — driven by include keywords."""
        if not pages or not _SCENE_KEYWORDS:
            return []

        evidence: list[Evidence] = []
        seen_scenes: set[str] = set()

        for page in pages:
            for text_block in page.texts:
                if text_block.level.value not in ("title", "h1", "h2"):
                    continue
                content = text_block.content
                for scene, kws in _SCENE_KEYWORDS.items():
                    if scene in seen_scenes:
                        continue
                    for kw in kws[:20]:  # only check first 20 keywords per category for speed
                        if len(kw) >= 4 and kw in content:
                            base = 0.20 if text_block.level.value in ("title", "h1") else 0.15
                            evidence.append(Evidence(
                                source="visual",
                                category=scene,
                                weight=base,
                                direction=1,
                                detail=f"heading keyword '{kw}' in {text_block.level.value}",
                            ))
                            seen_scenes.add(scene)
                            break

        return evidence

    # ─── Evidence Fusion ───

    def _fuse_evidence(self, evidence_list: list[Evidence]) -> tuple[str, float, list[dict]]:
        """
        Fuse all evidence signals into a final verdict.

        Algorithm (softmax-based):
            1. Separate positive evidence and exclusion evidence
            2. Exclusions are hard vetoes: remove any category with exclusion
            3. Positive evidence is summed per category, then normalized
            4. Confidence = best_score / (best_score + second_best_score + epsilon)
            5. If gap between top 2 < 0.15, mark as ambiguous
        """
        if not evidence_list:
            return "generic", 0.0, []

        # Hard veto: identify eliminated categories
        vetoed: set[str] = set()
        positive: list[Evidence] = []
        for ev in evidence_list:
            if ev.direction == -1:
                vetoed.add(ev.category)
            else:
                positive.append(ev)

        # Sum positive evidence per category
        scores: dict[str, float] = {}
        for ev in positive:
            if ev.category in vetoed:
                continue
            scores[ev.category] = scores.get(ev.category, 0.0) + ev.weight

        if not scores:
            return "generic", 0.0, [ev.to_dict() for ev in evidence_list]

        # Sort by score descending
        sorted_scores = sorted(scores.items(), key=lambda x: -x[1])
        best_scene, best_score = sorted_scores[0]
        second_score = sorted_scores[1][1] if len(sorted_scores) >= 2 else 0.0

        # Softmax-like relative confidence
        epsilon = 0.001
        rel_confidence = best_score / (best_score + second_score + epsilon)
        
        # Absolute confidence: keyword hit ratio for best category
        # Count positive evidence items for best_scene vs total
        best_count = sum(1 for ev in positive if ev.category == best_scene)
        unique_categories = len({ev.category for ev in positive})
        # abs_confidence = how many evidence dimensions fired for best vs total
        abs_confidence = best_count / max(len(positive), 1)
        
        # Fuse: 70% relative + 30% absolute
        confidence = 0.7 * rel_confidence + 0.3 * abs_confidence

        # Ambiguous detection
        gap = (best_score - second_score) / max(best_score, epsilon)
        fused_evidence = [ev.to_dict() for ev in evidence_list]
        fused_evidence.append({
            "source": "fusion",
            "category": "_decision",
            "weight": round(confidence, 3),
            "direction": 1,
            "detail": (
                f"best={best_scene}({best_score:.3f}) "
                f"second={sorted_scores[1][0] if len(sorted_scores) >= 2 else 'none'}({second_score:.3f}) "
                f"gap={gap:.3f} vetoed={sorted(vetoed)}"
            ),
        })

        if gap < 0.15 and len(sorted_scores) >= 2:
            # Ambiguous — but still return best scene, confidence will be low
            logger.info(f"[EvidenceEngine] Ambiguous: {best_scene} vs {sorted_scores[1][0]} (gap={gap:.3f})")

        return best_scene, confidence, fused_evidence


