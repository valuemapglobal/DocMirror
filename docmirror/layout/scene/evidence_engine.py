# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Evidence engine — accumulates and weighs classification evidence.

Purpose: Collects ``Evidence`` objects from rules and plugins, scores them,
and supports conflict resolution for scene classification.

Main components: ``EvidenceEngine``, ``Evidence``.

Upstream: ``scene.rules``, plugin signals, OCR text.

Downstream: ``scene.scene_resolver``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from docmirror.framework.middlewares.base import BaseMiddleware
from docmirror.layout.scene.evidence_types import Evidence
from docmirror.runtime.debug_artifact import is_debug_mode

from ...models.entities.parse_result import ParseResult

logger = logging.getLogger(__name__)

from docmirror.configs.scene.loader import (
    compute_keyword_uniqueness,
    get_scene_evidence_specs,
    get_scene_excludes,
    get_scene_includes,
)
from docmirror.layout.scene.evidence_types import Evidence

# ═══════════════════════════════════════════════════════════════════════════════
# EvidenceEngine Middleware
# ═══════════════════════════════════════════════════════════════════════════════


class EvidenceEngine(BaseMiddleware):
    """
    Multi-dimensional evidence-based document classification.

    Collects classification evidence from:
        - keyword matching (include + exclude)
        - table header structure
        - entity field presence
        - visual/typographic features
        - metadata (page count, file type)

    Evidence is fused via softmax-based confidence calculation.
    """

    def process(self, result: ParseResult) -> ParseResult:
        """Collect evidence, fuse, and set document_type."""
        old_doc_type = result.entities.document_type
        all_evidence: list[Evidence] = []
        forced_hint = self._forced_user_hint(result)

        # Phase 1: Collect evidence from all sources
        classification_text = result.full_text
        cover_text = self._cover_page_text(result)
        if cover_text:
            # Cover letter / title block often holds issuer keywords omitted from table cells.
            classification_text = f"{cover_text}\n{classification_text}"
        all_evidence.extend(self._keyword_evidence(classification_text))
        all_evidence.extend(self._text_frame_evidence(classification_text, cover_text))
        all_evidence.extend(self._header_evidence(result.all_tables()))
        all_evidence.extend(self._user_hint_evidence(result))
        all_evidence.extend(self._extractor_scene_evidence(result))
        if not forced_hint:
            all_evidence.extend(self._filename_evidence(result))
        all_evidence.extend(self._entity_evidence(result.kv_entities))
        all_evidence.extend(self._visual_evidence(result.pages))

        # Phase 2: Fuse evidence (extractor scene hint shields its category from keyword veto)
        protected = self._protected_extractor_categories(result, include_filename=not forced_hint)
        verdict, confidence, fused_evidence = self._fuse_evidence(
            all_evidence,
            protected=protected,
        )

        # Phase 3: Apply verdict
        doc_type = verdict if confidence >= 0.3 else "generic"
        if forced_hint:
            doc_type = forced_hint
            confidence = max(confidence, 0.99)
        result.entities.document_type = doc_type

        # Phase 3b: Refine layout profile hint for ledger archetypes (does not re-extract)
        from docmirror.layout.scene.scene_resolver import scene_to_layout_profile_id

        refined_profile = scene_to_layout_profile_id(doc_type)
        canonical_doc_type = self._canonical_document_type(doc_type)
        ds = result.entities.domain_specific
        if not isinstance(ds, dict):
            ds = {}
        if canonical_doc_type != doc_type:
            ds["canonical_document_type"] = canonical_doc_type
        else:
            ds.pop("canonical_document_type", None)
        if refined_profile:
            ds["document_scene_refined"] = doc_type
            ds["layout_profile_id_refined"] = refined_profile
            ds["layout_profile_refine_confidence"] = confidence
        if forced_hint:
            ds["classification_source"] = "user_hint_force"
        hint_value, hint_strength = self._user_hint(result)
        conflicts = [
            ev.to_dict() for ev in all_evidence if ev.direction == 1 and ev.category != doc_type and ev.weight >= 0.2
        ][:10]
        ds["classification_provenance"] = {
            "document_type": doc_type,
            "confidence": round(confidence, 3),
            "source": "user_hint_force" if forced_hint else ("user_hint+evidence" if hint_value else "evidence"),
            "hint": ({"value": hint_value, "strength": hint_strength, "source": "user"} if hint_value else None),
            "conflicts": conflicts,
            "fusion": fused_evidence[-1] if fused_evidence else None,
        }
        if ds:
            result.entities.domain_specific = ds

        # Evidence log for debugging (mirror/API only when DOCMIRROR_DEBUG=1)
        if (
            is_debug_mode()
            and hasattr(result.entities, "domain_specific")
            and isinstance(result.entities.domain_specific, dict)
        ):
            result.entities.domain_specific["evidence_log"] = fused_evidence

        # EHL annex (debug only — excluded from mirror.json via exclude=True)
        if is_debug_mode():
            from docmirror.models.ehl import attach_classification_annex

            attach_classification_annex(result, all_evidence, selected_category=doc_type)

        result.record_mutation(
            middleware_name=self.name,
            target_block_id="document",
            field_changed="entities",
            old_value=old_doc_type,
            new_value=doc_type,
            confidence=confidence,
            reason=f"evidence_fusion (best={verdict}, conf={confidence:.2f})",
        )

        logger.info(f"[EvidenceEngine] {doc_type} (conf={confidence:.2f}) | {len(all_evidence)} evidence items")
        return result

    @staticmethod
    def _canonical_document_type(document_type: str) -> str:
        """Map plugin-declared aliases to edition-facing document types."""
        from docmirror.configs.scene.loader import get_scene_aliases

        return get_scene_aliases().get(document_type, document_type)

    def _cover_page_text(self, result: ParseResult) -> str:
        """First-page narrative text + table headers (issuer lines often live here)."""
        if not result.pages:
            return ""
        page = result.pages[0]
        parts: list[str] = []
        for block in page.texts:
            if block.content:
                parts.append(block.content)
        for table in page.tables:
            if table.headers:
                parts.extend(str(h) for h in table.headers if h)
        return "\n".join(parts)

    def _extractor_scene_hint(self, result: ParseResult) -> tuple[str | None, float]:
        """Extractor/EPO scene hint attached during Mirror extraction."""
        ds = getattr(result.entities, "domain_specific", None) or {}
        if not isinstance(ds, dict):
            return None, 0.0
        scene = ds.get("extractor_scene_hint") or ds.get("pre_analyzer_scene_hint")
        if not scene or scene in ("unknown", "generic"):
            return None, 0.0
        confidence = float(ds.get("extractor_scene_confidence") or 0.85)
        return str(scene), confidence

    def _user_hint(self, result: ParseResult) -> tuple[str | None, str]:
        ds = getattr(result.entities, "domain_specific", None) or {}
        if not isinstance(ds, dict):
            return None, "prefer"
        hint = ds.get("user_doc_type_hint")
        if not hint:
            return None, "prefer"
        strength = str(ds.get("user_doc_type_hint_strength") or "prefer")
        return str(hint), strength

    def _forced_user_hint(self, result: ParseResult) -> str | None:
        hint, strength = self._user_hint(result)
        if hint and strength == "force":
            return hint
        return None

    def _user_hint_evidence(self, result: ParseResult) -> list[Evidence]:
        hint, strength = self._user_hint(result)
        if not hint or strength == "force":
            return []
        return [
            Evidence(
                source="user_hint",
                category=hint,
                weight=0.45,
                direction=1,
                detail=f"user doc_type_hint={hint}",
            )
        ]

    def _text_frame_evidence(self, document_text: str, cover_text: str) -> list[Evidence]:
        """Evaluate document/cover signatures declared by plugin scene resources."""
        evidence: list[Evidence] = []
        for scene, spec in get_scene_evidence_specs().items():
            for rule in spec.get("text_signatures") or []:
                if not isinstance(rule, dict):
                    continue
                scope = str(rule.get("scope") or "document")
                source_text = cover_text if scope == "cover" else document_text
                compact = re.sub(r"\s+", "", source_text or "")
                if not compact:
                    continue
                required = [str(value) for value in rule.get("required") or [] if str(value)]
                if required and not all(re.sub(r"\s+", "", value) in compact for value in required):
                    continue
                candidate_pattern = str(rule.get("candidate_pattern") or "")
                candidate_field_type = str(rule.get("candidate_field_type") or "")
                if candidate_pattern and candidate_field_type:
                    from docmirror.ocr.correction.validator_registry import ValidatorRegistry

                    candidates = re.findall(candidate_pattern, compact)
                    outcomes = [
                        ValidatorRegistry.default().evaluate(
                            str(candidate),
                            field_type=candidate_field_type,
                            country=str(rule.get("candidate_country") or "") or None,
                        )
                        for candidate in candidates
                    ]
                    if not any(outcome is not None and outcome.valid for outcome in outcomes):
                        continue
                groups = [group for group in rule.get("signal_groups") or [] if isinstance(group, list)]
                matched = [
                    [str(token) for token in group if str(token) and re.sub(r"\s+", "", str(token)) in compact]
                    for group in groups
                ]
                matched = [tokens for tokens in matched if tokens]
                if len(matched) < int(rule.get("min_matches") or len(groups)):
                    continue
                weight = float(rule.get("weight") or 0.0)
                for threshold, tier_weight in (rule.get("weight_tiers") or {}).items():
                    if len(matched) >= int(threshold):
                        weight = max(weight, float(tier_weight))
                evidence.append(
                    Evidence(
                        source=str(rule.get("source") or f"{scope}_frame"),
                        category=scene,
                        weight=weight,
                        direction=1,
                        detail=f"plugin text signature matched {len(matched)}/{len(groups)} groups",
                    )
                )
        return evidence

    def _protected_extractor_categories(
        self,
        result: ParseResult,
        *,
        include_filename: bool = True,
    ) -> set[str]:
        """Categories backed by high-confidence extractor hints skip keyword_exclude veto."""
        protected: set[str] = set()
        scene, confidence = self._extractor_scene_hint(result)
        if scene and confidence >= 0.70:
            protected.add(scene)
        if include_filename:
            file_name = self._source_file_name(result)
            for category, spec in get_scene_evidence_specs().items():
                if any(str(token) in file_name for token in spec.get("filename_tokens") or []):
                    protected.add(category)
        return protected

    def _filename_evidence(self, result: ParseResult) -> list[Evidence]:
        """Filename tokens (issuer uploads often encode doc type in the name)."""
        file_name = self._source_file_name(result)
        if not file_name:
            return []
        evidence: list[Evidence] = []
        for category, spec in get_scene_evidence_specs().items():
            for token in spec.get("filename_tokens") or []:
                if str(token) not in file_name:
                    continue
                evidence.append(
                    Evidence(
                        source="filename",
                        category=category,
                        weight=0.40,
                        direction=1,
                        detail=f"filename token {token} in {file_name}",
                    )
                )
        return evidence

    @staticmethod
    def _source_file_name(result: ParseResult) -> str:
        """Resolve the original filename from canonical provenance or an explicit override."""
        ds = getattr(result.entities, "domain_specific", None) or {}
        file_name = str(ds.get("source_file_name") or "")
        if file_name:
            return Path(file_name).name
        return Path(result.file_path).name if result.file_path else ""

    def _extractor_scene_evidence(self, result: ParseResult) -> list[Evidence]:
        """Use extractor/EPO scene hint when extraction already resolved the archetype."""
        scene, confidence = self._extractor_scene_hint(result)
        if not scene or confidence < 0.70:
            return []
        weight = min(0.55, 0.30 + confidence * 0.25)
        return [
            Evidence(
                source="extractor_scene",
                category=scene,
                weight=weight,
                direction=1,
                detail=f"extractor scene_hint={scene} conf={confidence:.2f}",
            )
        ]

    # ─── Keyword Evidence (with exclusion veto) ───

    def _keyword_evidence(self, full_text: str) -> list[Evidence]:
        """Collect keyword-based evidence: include positive, exclude is veto."""
        if not full_text:
            return []

        evidence: list[Evidence] = []
        includes = get_scene_includes()
        excludes = get_scene_excludes()

        if not includes:
            return []

        # PDF text extraction often inserts a newline between every visual word
        # (for example ``Business\nLicense``).  Match against a whitespace-free
        # view as well as the original text so layout artifacts do not reroute a
        # known Community document into an unrelated generic scene.
        compact_text = re.sub(r"\s+", "", full_text)

        def keyword_matches(keyword: str) -> bool:
            if keyword in full_text:
                return True
            compact_keyword = re.sub(r"\s+", "", keyword)
            return len(compact_keyword) >= 3 and compact_keyword in compact_text

        # Precompute uniqueness weights
        if not hasattr(self, "_kw_uniqueness"):
            self._kw_uniqueness = compute_keyword_uniqueness()

        # Include keyword scoring
        for scene, kws in includes.items():
            score = 0.0
            matched = []
            for kw in kws:
                if keyword_matches(kw):
                    matched.append(kw)
                    uniqueness = self._kw_uniqueness.get(kw, 0.5)
                    lf = 3 if len(kw) >= 8 else (2 if len(kw) >= 5 else 1)
                    score += uniqueness * lf
            if score >= 0.5:
                evidence.append(
                    Evidence(
                        source="keyword",
                        category=scene,
                        weight=min(score / 10.0, 0.95),
                        direction=1,
                        detail=f"include matches: {matched} (score={score:.1f})",
                    )
                )

        # Exclusion (hard veto)
        for scene, kws in excludes.items():
            matched = [kw for kw in kws if keyword_matches(kw)]
            if matched:
                evidence.append(
                    Evidence(
                        source="keyword_exclude",
                        category=scene,
                        weight=100.0,  # absolute veto
                        direction=-1,
                        detail=f"hard veto by exclusion: {matched}",
                    )
                )

        return evidence

    # ─── Header Evidence ───

    def _header_evidence(self, table_blocks) -> list[Evidence]:
        """Match table headers against known column-name signatures."""
        if not table_blocks:
            return []

        scene_specs = get_scene_evidence_specs()

        evidence: list[Evidence] = []

        for scene, spec in scene_specs.items():
            feature_groups = spec.get("header_signatures") or []
            for table in table_blocks:
                if not table.headers:
                    continue
                header_set = {str(h).strip() for h in table.headers if h}
                best_conf = 0.0
                best_matched = 0
                best_required_len = 0
                for required in feature_groups:
                    if not isinstance(required, list) or not required:
                        continue
                    matched = 0
                    for req_kw in required:
                        for h in header_set:
                            if not self._header_keyword_match(req_kw, h):
                                continue
                            matched += 1
                            break
                    if matched >= len(required) * 0.6:
                        conf = min(0.35, 0.15 + 0.04 * matched)
                        if conf > best_conf:
                            best_conf = conf
                            best_matched = matched
                            best_required_len = len(required)
                if best_conf > 0:
                    evidence.append(
                        Evidence(
                            source="header",
                            category=scene,
                            weight=best_conf,
                            direction=1,
                            detail=f"matched {best_matched}/{best_required_len} header columns",
                        )
                    )
                    break

        return evidence

    @staticmethod
    def _header_keyword_match(req_kw: str, header: str) -> bool:
        """Match normalized complete headers without domain-specific exceptions."""

        def normalize(value: str) -> str:
            return re.sub(r"[\s_:：/\\-]+", "", str(value or "")).casefold()

        return bool(normalize(req_kw)) and normalize(req_kw) == normalize(header)

    # ─── Entity Evidence ───

    def _entity_evidence(self, entities) -> list[Evidence]:
        """Use plugin-owned entity-key signatures to classify document type."""
        if not entities:
            return []

        # Handle different entity access patterns
        if isinstance(entities, dict):
            keys = set(entities.keys())
        elif hasattr(entities, "kv_entities") and entities.kv_entities:
            keys = set(entities.kv_entities.keys())
        else:
            return []

        evidence: list[Evidence] = []
        for category, spec in get_scene_evidence_specs().items():
            for signature in spec.get("entity_signatures") or []:
                if not isinstance(signature, dict):
                    continue
                fields = {str(value) for value in signature.get("fields") or []}
                matched = len(keys & fields)
                if matched < int(signature.get("min_matches") or len(fields)):
                    continue
                base = float(signature.get("base_weight") or 0.10)
                per_match = float(signature.get("per_match_weight") or 0.05)
                max_weight = float(signature.get("max_weight") or 0.25)
                evidence.append(
                    Evidence(
                        source="entity",
                        category=category,
                        weight=min(base + per_match * matched, max_weight),
                        direction=1,
                        detail=f"plugin entity signature matched {matched}/{len(fields)} fields",
                    )
                )

        return evidence

    def _visual_evidence(self, pages) -> list[Evidence]:
        """Use title/heading text to boost confidence — driven by include keywords."""
        includes = get_scene_includes()
        if not pages or not includes:
            return []

        evidence: list[Evidence] = []
        seen_scenes: set[str] = set()

        for page in pages:
            for text_block in page.texts:
                if text_block.level.value not in ("title", "h1", "h2"):
                    continue
                content = text_block.content
                for scene, kws in includes.items():
                    if scene in seen_scenes:
                        continue
                    for kw in kws[:20]:  # only check first 20 keywords per category for speed
                        if len(kw) >= 4 and kw in content:
                            base = 0.20 if text_block.level.value in ("title", "h1") else 0.15
                            evidence.append(
                                Evidence(
                                    source="visual",
                                    category=scene,
                                    weight=base,
                                    direction=1,
                                    detail=f"heading keyword '{kw}' in {text_block.level.value}",
                                )
                            )
                            seen_scenes.add(scene)
                            break

        return evidence

    # ─── Evidence Fusion ───

    def _fuse_evidence(
        self,
        evidence_list: list[Evidence],
        *,
        protected: set[str] | None = None,
    ) -> tuple[str, float, list[dict]]:
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

        protected = protected or set()

        # Hard veto: identify eliminated categories
        vetoed: set[str] = set()
        positive: list[Evidence] = []
        for ev in evidence_list:
            if ev.direction == -1:
                if ev.category not in protected:
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
        # abs_confidence = how many evidence dimensions fired for best vs total
        abs_confidence = best_count / max(len(positive), 1)

        # Blend relative (70%) and absolute (30%) scores
        confidence = 0.7 * rel_confidence + 0.3 * abs_confidence

        # Ambiguous detection
        gap = (best_score - second_score) / max(best_score, epsilon)
        fused_evidence = [ev.to_dict() for ev in evidence_list]
        fused_evidence.append(
            {
                "source": "fusion",
                "category": "_decision",
                "weight": round(confidence, 3),
                "direction": 1,
                "detail": (
                    f"best={best_scene}({best_score:.3f}) "
                    f"second={sorted_scores[1][0] if len(sorted_scores) >= 2 else 'none'}({second_score:.3f}) "
                    f"gap={gap:.3f} vetoed={sorted(vetoed)}"
                ),
            }
        )

        if gap < 0.15 and len(sorted_scores) >= 2:
            second_scene = sorted_scores[1][0]
            logger.info(f"[EvidenceEngine] Ambiguous: {best_scene} vs {second_scene} (gap={gap:.3f})")
            best_scene, best_score, second_score = self._disambiguate_classification_group(
                sorted_scores,
                positive,
                vetoed,
                best_scene,
                best_score,
                second_score,
            )
            rel_confidence = best_score / (best_score + second_score + epsilon)
            best_count = sum(1 for ev in positive if ev.category == best_scene)
            abs_confidence = best_count / max(len(positive), 1)
            confidence = 0.7 * rel_confidence + 0.3 * abs_confidence

        return best_scene, confidence, fused_evidence

    def _disambiguate_classification_group(
        self,
        sorted_scores: list[tuple[str, float]],
        positive: list[Evidence],
        vetoed: set[str],
        best_scene: str,
        best_score: float,
        second_score: float,
    ) -> tuple[str, float, float]:
        """Break plugin-declared classification-group ties using header evidence."""
        if len(sorted_scores) < 2:
            return best_scene, best_score, second_score
        top, second = sorted_scores[0][0], sorted_scores[1][0]
        specs = get_scene_evidence_specs()
        top_group = str(specs.get(top, {}).get("ambiguity_group") or "")
        if not top_group or top_group != str(specs.get(second, {}).get("ambiguity_group") or ""):
            return best_scene, best_score, second_score

        score_map = dict(sorted_scores)
        top_score = score_map.get(top, 0.0)
        runner_up_score = score_map.get(second, 0.0)

        header_weight = {top: 0.0, second: 0.0}
        for ev in positive:
            if ev.source == "header" and ev.category in header_weight:
                header_weight[ev.category] += ev.weight

        top_headers = header_weight[top]
        runner_up_headers = header_weight[second]
        if top_headers > runner_up_headers + 0.05:
            return top, top_score, runner_up_score
        if runner_up_headers > top_headers + 0.05:
            return second, runner_up_score, top_score

        if top in vetoed and second not in vetoed:
            return second, runner_up_score, top_score
        if second in vetoed and top not in vetoed:
            return top, top_score, runner_up_score

        return best_scene, best_score, second_score
