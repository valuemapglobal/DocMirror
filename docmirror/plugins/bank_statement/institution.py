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

Dependencies: ``core.profile.registry``, ``configs.models.layout_profile``,
``configs/yaml/bank_statement/institution_overrides.yaml``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from docmirror.configs.models.layout_profile import InstitutionVariant, LayoutProfile
from docmirror.core.profile.registry import (
    get_profile,
    load_profiles,
    match_institution_variant,
    resolve_header_aliases,
)

_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "configs" / "yaml" / "bank_statement" / "institution_overrides.yaml"
)


@lru_cache(maxsize=1)
def _load_plugin_config() -> dict[str, Any]:
    if not _CONFIG_PATH.is_file():
        return {"source_profile": "borderless_ledger_bank", "overrides": {}}
    with open(_CONFIG_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


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
