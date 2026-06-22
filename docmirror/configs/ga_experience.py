# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""GA demo and fixture-bank configuration helpers."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from docmirror.configs.paths import GA_DEMO_MANIFEST_YAML, REAL_WORLD_FIXTURE_BANK_YAML


@lru_cache(maxsize=1)
def load_ga_demo_manifest() -> dict[str, Any]:
    if not GA_DEMO_MANIFEST_YAML.is_file():
        return {"version": 1, "demos": {}}
    return yaml.safe_load(GA_DEMO_MANIFEST_YAML.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=1)
def load_real_world_fixture_bank() -> dict[str, Any]:
    if not REAL_WORLD_FIXTURE_BANK_YAML.is_file():
        return {"version": 1, "fixtures": [], "source_types": [], "quality_buckets": []}
    return yaml.safe_load(REAL_WORLD_FIXTURE_BANK_YAML.read_text(encoding="utf-8")) or {}


def invalidate_ga_experience_cache() -> None:
    load_ga_demo_manifest.cache_clear()
    load_real_world_fixture_bank.cache_clear()
