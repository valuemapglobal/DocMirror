# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SSO threshold loader — YAML SSOT with safe defaults."""

from __future__ import annotations

from functools import lru_cache

import yaml

from docmirror.configs.paths import YAML_DIR

_DEFAULTS = {
    "pipe_grid_veto_threshold": 0.85,
    "pipe_grid_enrich_threshold": 0.85,
    "scene_hint_prior_delta": 0.05,
}


@lru_cache(maxsize=1)
def load_sso_config() -> dict:
    path = YAML_DIR / "sso.yaml"
    if not path.is_file():
        return dict(_DEFAULTS)
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    out = dict(_DEFAULTS)
    out.update({k: data[k] for k in _DEFAULTS if k in data})
    return out


def pipe_grid_veto_threshold() -> float:
    return float(load_sso_config()["pipe_grid_veto_threshold"])


def pipe_grid_enrich_threshold() -> float:
    return float(load_sso_config()["pipe_grid_enrich_threshold"])


def scene_hint_prior_delta() -> float:
    return float(load_sso_config()["scene_hint_prior_delta"])
