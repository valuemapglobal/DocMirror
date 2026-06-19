# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Profile registry — loads and inherits extraction profiles.

Purpose: Deep-merges profile inheritance chains and exposes ``get_profile``,
``match_layout_profile``, and document-type mapping helpers.

Main components: ``load_profiles``, ``get_profile``, ``match_layout_profile``.

Upstream: Profile config on disk.

Downstream: ``profile.resolver``, ``pipeline.document_profile``.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

import yaml

from docmirror.models.entities.extraction_profile import ExtractionProfile
from docmirror.models.entities.layout_profile import InstitutionVariant, LayoutProfile, LayoutProfileMatchRules

logger = logging.getLogger(__name__)

from docmirror.configs.paths import LAYOUT_PROFILES_YAML as _CONFIG_PATH


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if k == "inherits":
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _resolve_inheritance(raw_profiles: dict[str, dict[str, Any]]) -> dict[str, ExtractionProfile]:
    resolved: dict[str, ExtractionProfile] = {}
    cache: dict[str, dict[str, Any]] = {}

    def _resolve(pid: str) -> dict[str, Any]:
        if pid in cache:
            return cache[pid]
        spec = dict(raw_profiles.get(pid, {}))
        parent_id = spec.get("inherits")
        if parent_id and parent_id in raw_profiles:
            base = _resolve(parent_id)
            merged = _deep_merge(base, spec)
        else:
            merged = spec
        merged["profile_id"] = pid
        cache[pid] = merged
        return merged

    for pid in raw_profiles:
        data = _resolve(pid)
        match_raw = data.pop("match", None)
        match_rules = LayoutProfileMatchRules(**match_raw) if match_raw else None
        data["profile_id"] = pid
        if match_rules:
            data["match"] = match_rules
        variants_raw = data.pop("institution_variants", None) or []
        variants: list[InstitutionVariant] = []
        for item in variants_raw:
            if isinstance(item, dict):
                variants.append(InstitutionVariant(**item))
        data["institution_variants"] = variants
        resolved[pid] = ExtractionProfile(**{k: v for k, v in data.items() if k != "inherits"})
    return resolved


@lru_cache(maxsize=1)
def load_profiles() -> dict[str, ExtractionProfile]:
    """Load and cache all layout profiles from YAML."""
    if not _CONFIG_PATH.exists():
        logger.warning("[LayoutProfile] Config not found: %s — using generic only", _CONFIG_PATH)
        return {"generic": ExtractionProfile(profile_id="generic")}
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    profiles_raw = raw.get("profiles", {})
    return _resolve_inheritance(profiles_raw)


def get_profile(profile_id: str) -> ExtractionProfile:
    profiles = load_profiles()
    return profiles.get(profile_id, profiles["generic"])


def document_type_for_profile(profile_id: str) -> str | None:
    """Lightweight document type hint for pre-middleware (MIRROR) exports."""
    profile = get_profile(profile_id)
    if profile.document_type_hint:
        return profile.document_type_hint
    if profile.match and profile.match.scene_hint:
        return profile.match.scene_hint
    return None


def match_layout_profile(
    *,
    text_sample: str = "",
    num_pages: int = 0,
    content_type: str = "unknown",
    scene_hint: str = "unknown",
    force_profile: str | None = None,
    resolved_scene: str | None = None,
    scene_confidence: float = 0.0,
) -> ExtractionProfile:
    """Select the best matching layout profile.

    Order:
        1. ``DOCMIRROR_LAYOUT_PROFILE`` env or ``force_profile`` arg
        2. High-confidence ``resolved_scene`` from SceneResolver (same corpus as EvidenceEngine)
        3. YAML match rules (text/min_pages)
        4. ``scene_hint`` fallback (PreAnalyzer lightweight)
        5. generic fallback
    """
    profiles = load_profiles()
    env_force = os.environ.get("DOCMIRROR_LAYOUT_PROFILE", "").strip()
    forced = force_profile or (env_force if env_force and env_force != "auto" else None)
    if forced and forced in profiles:
        return profiles[forced]

    if resolved_scene and resolved_scene not in ("unknown", "generic") and scene_confidence >= 0.75:
        from docmirror.core.scene.scene_resolver import scene_to_layout_profile_id

        mapped = scene_to_layout_profile_id(resolved_scene)
        if mapped and mapped in profiles:
            logger.info(
                "[LayoutProfile] SceneResolver → profile=%s (scene=%s conf=%.2f)",
                mapped,
                resolved_scene,
                scene_confidence,
            )
            return profiles[mapped]

    text = text_sample or ""
    for pid, profile in profiles.items():
        if pid == "generic":
            continue
        rules = profile.match
        if not rules:
            continue
        if not _rules_match(rules, text=text, num_pages=num_pages, content_type=content_type, scene_hint=scene_hint):
            continue
        logger.info("[LayoutProfile] Matched profile=%s (pages=%d)", pid, num_pages)
        return profile

    if scene_hint == "wechat_payment" and "borderless_ledger_wechat" in profiles:
        return profiles["borderless_ledger_wechat"]

    if scene_hint == "alipay_payment" and "borderless_ledger_alipay" in profiles:
        return profiles["borderless_ledger_alipay"]

    if scene_hint in ("bank_statement", "bank_reconciliation") and "borderless_ledger_bank" in profiles:
        return profiles["borderless_ledger_bank"]

    return profiles["generic"]


def _rules_match(
    rules: LayoutProfileMatchRules,
    *,
    text: str,
    num_pages: int,
    content_type: str,
    scene_hint: str,
) -> bool:
    if rules.min_pages and num_pages < rules.min_pages:
        return False
    if rules.content_type and rules.content_type != content_type:
        return False
    if rules.scene_hint and rules.scene_hint != scene_hint:
        return False
    if rules.text_all and not all(kw in text for kw in rules.text_all):
        return False
    if rules.text_any and not any(kw in text for kw in rules.text_any):
        return False
    if not rules.text_any and not rules.text_all and not rules.scene_hint and not rules.content_type:
        return False
    return True


def should_skip_cross_page_merge(profile: LayoutProfile | None, explicit: bool | None = None) -> bool:
    """Resolve skip_cross_page_merge for extract() / MIRROR export."""
    if explicit is not None:
        return explicit
    if profile is None:
        return False
    return profile.mirror_skip_cross_page_merge


def is_borderless_ledger_profile(profile: LayoutProfile | None) -> bool:
    """True for wechat/bank borderless ledger profiles (fast merge + parallel postprocess)."""
    if profile is None:
        return False
    return profile.profile_id.startswith("borderless_ledger")


def match_institution_variant(
    profile: LayoutProfile | None,
    text_sample: str,
) -> InstitutionVariant | None:
    """Pick the best institution variant for a layout profile (bank-specific column maps)."""
    if profile is None or not text_sample or not profile.institution_variants:
        return None
    text = text_sample
    best: InstitutionVariant | None = None
    best_score = 0
    for variant in profile.institution_variants:
        score = 0
        for kw in variant.keywords:
            if kw and kw in text:
                score += len(kw)
        if score > best_score:
            best_score = score
            best = variant
    return best if best_score > 0 else None


def resolve_header_aliases(profile: LayoutProfile | None, header: str) -> str:
    """Map a raw header cell to canonical name using profile header_aliases."""
    if profile is None or not header:
        return header
    for canonical, aliases in profile.header_aliases.items():
        if header == canonical or header in aliases:
            return canonical
    return header
