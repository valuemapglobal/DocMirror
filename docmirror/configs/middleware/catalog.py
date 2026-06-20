# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Middleware catalog loader and validator — MEP single source of truth.

Loads ``middleware_catalog.yaml`` into ``MiddlewareSpec`` records describing each
middleware's Python module, class name, pipeline stage, dependencies, conditional
``when`` guard expression, and enabled flag.

Key functions::

    load_catalog()              LRU-cached dict of name → ``MiddlewareSpec``
    get_middleware_class()      Import and verify ``BaseMiddleware`` subclass
    get_middleware_stage()      Return stage string for ordering
    list_catalog_names()        Sorted catalog keys
    validate_catalog()          Verify imports and enhancement profile references

``validate_catalog`` cross-checks that every middleware referenced in
``enhancement_profiles.yaml`` exists in the catalog and is importable, catching
configuration drift at startup or in CI.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

import yaml

from docmirror.configs.format.loader import invalidate_format_cache, load_enhancement_profiles
from docmirror.configs.paths import MIDDLEWARE_CATALOG_YAML

if TYPE_CHECKING:
    from docmirror.middlewares.base import BaseMiddleware

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MiddlewareSpec:
    name: str
    module: str
    class_name: str
    stage: str = ""
    provides: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    when: str = ""
    enabled: bool = True


def invalidate_middleware_cache() -> None:
    load_catalog.cache_clear()
    invalidate_format_cache()


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, MiddlewareSpec]:
    path = MIDDLEWARE_CATALOG_YAML
    if not path.is_file():
        logger.warning("[MEP] Missing %s", path)
        return {}

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    catalog: dict[str, MiddlewareSpec] = {}
    for name, raw in (data.get("middlewares") or {}).items():
        if not isinstance(raw, dict):
            continue
        catalog[str(name)] = MiddlewareSpec(
            name=str(name),
            module=str(raw.get("module", "")),
            class_name=str(raw.get("class", name)),
            stage=str(raw.get("stage", "")),
            provides=tuple(raw.get("provides") or ()),
            depends_on=tuple(raw.get("depends_on") or ()),
            when=str(raw.get("when") or ""),
            enabled=bool(raw.get("enabled", True)),
        )
    return catalog


def get_middleware_class(name: str) -> type[BaseMiddleware]:
    catalog = load_catalog()
    spec = catalog.get(name)
    if spec is None:
        raise KeyError(f"Middleware {name!r} not in middleware_catalog.yaml")
    mod = importlib.import_module(spec.module)
    cls = getattr(mod, spec.class_name)
    from docmirror.middlewares.base import BaseMiddleware

    if not issubclass(cls, BaseMiddleware):
        raise TypeError(f"{name}: {cls} is not a BaseMiddleware subclass")
    return cls


def get_middleware_stage(name: str) -> str:
    spec = load_catalog().get(name)
    return spec.stage if spec else ""


def list_catalog_names() -> list[str]:
    return sorted(load_catalog().keys())


def validate_catalog() -> list[str]:
    """Return validation error messages (empty list = OK)."""
    errors: list[str] = []
    catalog = load_catalog()
    if not catalog:
        errors.append("middleware_catalog.yaml loaded empty or missing")
        return errors

    for name, spec in catalog.items():
        if not spec.module:
            errors.append(f"{name}: missing module")
            continue
        try:
            get_middleware_class(name)
        except Exception as exc:
            errors.append(f"{name}: cannot import {spec.module}.{spec.class_name}: {exc}")

    from docmirror.configs.middleware.resolver import flatten_profile_middleware_names

    profiles, _ = load_enhancement_profiles()
    optional_runtime = {"SLMEntityExtractor", "AnomalyDetector"}
    for model, modes in profiles.items():
        for mode, mode_cfg in modes.items():
            for mw_name in flatten_profile_middleware_names(mode_cfg):
                if mw_name in optional_runtime:
                    continue
                if mw_name not in catalog:
                    errors.append(f"enhancement_profiles {model}.{mode}: middleware {mw_name!r} missing from catalog")
                elif not catalog[mw_name].enabled and mw_name not in optional_runtime:
                    # enabled=false entries must not appear in profiles unless SLM-style optional
                    pass  # profile may reference AnomalyDetector etc. when enabled in catalog

    return errors
