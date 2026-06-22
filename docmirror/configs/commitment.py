# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Open-source commitment matrix helpers."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from docmirror.configs.paths import OPEN_SOURCE_COMMITMENT_MATRIX_YAML


@lru_cache(maxsize=1)
def load_commitment_matrix() -> dict[str, Any]:
    if not OPEN_SOURCE_COMMITMENT_MATRIX_YAML.is_file():
        return {"version": 1, "commitments": {}, "rules": {}}
    return yaml.safe_load(OPEN_SOURCE_COMMITMENT_MATRIX_YAML.read_text(encoding="utf-8")) or {}


def commitment_summary() -> dict[str, Any]:
    data = load_commitment_matrix()
    commitments = data.get("commitments") or {}
    return {
        "version": data.get("version", 1),
        "community_core_domains": list(data.get("community_core_domains") or []),
        "license_missing_must_not_affect": list((data.get("rules") or {}).get("license_missing_must_not_affect") or []),
        "commitments": {
            key: {
                "community": _normalize_commitment_value(value.get("community")),
                "enterprise": _normalize_commitment_value(value.get("enterprise")),
                "finance": _normalize_commitment_value(value.get("finance")),
                "category": value.get("category"),
            }
            for key, value in commitments.items()
            if isinstance(value, dict)
        },
    }


def commitment_for_artifact() -> dict[str, Any]:
    summary = commitment_summary()
    return {
        "matrix_version": summary["version"],
        "community_core_domains": summary["community_core_domains"],
        "license_missing_must_not_affect": summary["license_missing_must_not_affect"],
    }


def invalidate_commitment_matrix_cache() -> None:
    load_commitment_matrix.cache_clear()


def _normalize_commitment_value(value: Any) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return str(value)
