# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Institution variant resolution for bank statement plugin parsers.

Loads ``institution_overrides.yaml``, resolves the active ``LayoutProfile``, matches
bank-specific variants from document text, and normalizes table headers per variant.

Pipeline role: ``header_resolve`` and style parsers call ``match_institution`` and
``normalize_table_headers`` to apply per-bank column alias overrides before extract.

Key exports: ``get_bank_layout_profile``, ``match_institution``,
``normalize_table_headers``.

Dependencies: ``layout.profile.registry``, ``configs.models.layout_profile``, and
the plugin-owned ``resources/institution_overrides.yaml``.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from importlib.resources import files
from typing import Any

import yaml

from docmirror.configs.models.layout_profile import InstitutionVariant, LayoutProfile
from docmirror.layout.profile.registry import (
    get_profile,
    load_profiles,
    match_institution_variant,
    resolve_header_aliases,
)

_CONFIG_PATH = files(__package__).joinpath("resources").joinpath("institution_overrides.yaml")
_INSTITUTIONS_PATH = files(__package__).joinpath("resources").joinpath("institutions.yaml")


@lru_cache(maxsize=1)
def _load_plugin_config() -> dict[str, Any]:
    if not _CONFIG_PATH.is_file():
        return {"source_profile": "borderless_ledger_bank", "overrides": {}}
    with _CONFIG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache(maxsize=1)
def _load_institution_registry() -> dict[str, dict[str, Any]]:
    if not _INSTITUTIONS_PATH.is_file():
        return {}
    with _INSTITUTIONS_PATH.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    institutions = raw.get("institutions") if isinstance(raw, dict) else None
    return institutions if isinstance(institutions, dict) else {}


def _header_area(full_text: str, max_chars: int = 5000) -> str:
    column_keywords = (
        "Transaction date",
        "凭证Type",
        "交易时间",
        "序号",
        "交易明细",
        "记账Date",
        "交易Type",
    )
    cut_pos = len(full_text)
    for keyword in column_keywords:
        index = full_text.find(keyword)
        if 15 < index < cut_pos:
            cut_pos = index
    return full_text[: min(cut_pos, max_chars)]


def detect_registered_institution(full_text: str) -> str | None:
    """Resolve a bank display name using only this plugin's institution asset."""
    registry = _load_institution_registry()
    if not full_text or not registry:
        return None
    normalized = unicodedata.normalize("NFKC", full_text)
    header_text = _header_area(normalized)

    for info in registry.values():
        keywords = info.get("identification_keywords") or []
        if keywords and all(str(keyword) in normalized for keyword in keywords):
            return str(info.get("name") or "") or None

    bank_context = ("流水", "对账单", "交易明细", "银行", "账号", "账户")
    if any(keyword in header_text for keyword in bank_context):
        regional_patterns = (
            r"([一-鿿]{2,6})(?:农商银行|农村商业银行|农商行)",
            r"([一-鿿]{2,6})(?:城商银行|城市商业银行)",
            r"([一-鿿]{2,6})(?:村镇银行)",
        )
        for pattern in regional_patterns:
            match = re.search(pattern, header_text)
            if match:
                return match.group(0)

    sorted_institutions = sorted(
        registry.values(),
        key=lambda info: len(str(info.get("name") or "")),
        reverse=True,
    )
    for info in sorted_institutions:
        name = str(info.get("name") or "")
        if name and name in header_text:
            return name
    for info in registry.values():
        name = str(info.get("name") or "")
        for alias in info.get("aliases") or []:
            if alias and str(alias) in header_text:
                return name or str(alias)
    return None


def get_bank_layout_profile() -> LayoutProfile | None:
    cfg = _load_plugin_config()
    profile_id = cfg.get("source_profile") or "borderless_ledger_bank"
    load_profiles.cache_clear()
    return get_profile(profile_id)


def match_institution(
    full_text: str,
    institution_hint: str | None = None,
) -> InstitutionVariant | None:
    profile = get_bank_layout_profile()
    if institution_hint and profile:
        for variant in profile.institution_variants:
            if variant.display_name == institution_hint or variant.id == institution_hint:
                return _apply_inline_override(variant)
    if profile and full_text:
        matched = match_institution_variant(profile, full_text)
        if matched:
            return _apply_inline_override(matched)
    return None


def _apply_inline_override(variant: InstitutionVariant) -> InstitutionVariant:
    cfg = _load_plugin_config()
    overrides = (cfg.get("overrides") or {}).get(variant.id) or {}
    if not overrides:
        return variant
    column_map = dict(variant.column_map)
    column_map.update(overrides.get("column_map") or {})
    return variant.model_copy(update={"column_map": column_map})


def normalize_table_headers(
    tables: list[list[list[str]]],
    *,
    profile: LayoutProfile | None = None,
    variant: InstitutionVariant | None = None,
) -> list[list[list[str]]]:
    """Apply institution column_map + profile header_aliases to table cells."""
    if profile is None:
        profile = get_bank_layout_profile()
    if profile is None and variant is None:
        return tables

    out: list[list[list[str]]] = []
    for tbl in tables:
        normalized_tbl: list[list[str]] = []
        for row in tbl:
            normalized_row: list[str] = []
            for cell in row:
                text = str(cell or "").strip()
                if variant and text in variant.column_map:
                    text = variant.column_map[text]
                if profile:
                    text = resolve_header_aliases(profile, text)
                normalized_row.append(text)
            normalized_tbl.append(normalized_row)
        out.append(normalized_tbl)
    return out
