# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Post-extract hook catalog loader (PEC layer).

Reads ``configs/yaml/post_extract.yaml`` into ``PostExtractHookSpec`` records,
resolves which hooks apply for a given document type/edition/extracted payload,
and dynamically imports hook classes.

Pipeline role: ``post_extract.runner`` calls ``resolve_post_extract_hooks`` then
``get_hook_class`` for each matching entry after main extract serialization.

Key exports: ``PostExtractHookSpec``, ``load_post_extract_catalog``,
``get_hook_class``, ``resolve_post_extract_hooks``.

Dependencies: ``configs.paths.POST_EXTRACT_YAML``, ``post_extract.base``.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Any

import yaml

from docmirror.configs.paths import POST_EXTRACT_YAML

logger = logging.getLogger(__name__)
_catalog_cache: dict[str, PostExtractHookSpec] | None = None
_catalog_mtime: float = 0.0


@dataclass(frozen=True)
class PostExtractHookSpec:
    hook_id: str
    module: str
    class_name: str
    when: str = ""
    mutates_mirror: bool = False
    provides: tuple[str, ...] = ()


def load_post_extract_catalog() -> dict[str, PostExtractHookSpec]:
    """Load and validate the post-extract hook catalog.

    GA 1.0 HOOK-01: Validates hook module paths at load time by attempting
    to import each hook class, logging warnings for misconfigurations.

    GA 1.0 HOOK-02: Auto-invalidates the catalog cache when the YAML file's
    mtime changes, so edits take effect without restart.

    Returns:
        Ordered mapping of hook_id -> PostExtractHookSpec.
    """
    global _catalog_cache, _catalog_mtime  # noqa: PLW0603

    current_mtime: float = POST_EXTRACT_YAML.stat().st_mtime if POST_EXTRACT_YAML.is_file() else 0.0
    if _catalog_cache is not None and current_mtime == _catalog_mtime:
        return _catalog_cache

    _catalog_mtime = current_mtime

    if not POST_EXTRACT_YAML.is_file():
        _catalog_cache = {}
        return {}
    with open(POST_EXTRACT_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    catalog: dict[str, PostExtractHookSpec] = {}
    for hook_id, raw in (data.get("hooks") or {}).items():
        if not isinstance(raw, dict):
            continue
        catalog[str(hook_id)] = PostExtractHookSpec(
            hook_id=str(hook_id),
            module=str(raw.get("module", "")),
            class_name=str(raw.get("class", hook_id)),
            when=str(raw.get("when") or ""),
            mutates_mirror=bool(raw.get("mutates_mirror", False)),
            provides=tuple(raw.get("provides") or ()),
        )

    # HOOK-01: Validate hook modules at load time (must happen before cache store)
    for hook_id, spec in catalog.items():
        try:
            get_hook_class(spec)
        except Exception as exc:
            logger.warning(
                "[PostExtractCatalog] Hook %s module validation failed: %s",
                hook_id,
                exc,
            )

    _catalog_cache = catalog
    return catalog


def get_hook_class(spec: PostExtractHookSpec) -> type:
    mod = importlib.import_module(spec.module)
    cls = getattr(mod, spec.class_name)
    from docmirror.plugins._runtime.post_extract.base import PostExtractHook

    if not issubclass(cls, PostExtractHook):
        raise TypeError(f"{spec.hook_id}: {cls} is not a PostExtractHook")
    return cls


def _eval_when(expr: str, ns: dict[str, Any]) -> bool:
    if not expr.strip():
        return True
    try:
        return bool(eval(expr, {"__builtins__": {}}, ns))
    except Exception as exc:
        logger.debug("[PostExtract] when guard failed for %r: %s", expr, exc)
        return False


def resolve_post_extract_hooks(
    *,
    document_type: str,
    edition: str,
    extracted: dict[str, Any],
) -> list[PostExtractHookSpec]:
    catalog = load_post_extract_catalog()
    ns = {
        "document_type": document_type,
        "edition": edition,
        "extracted": extracted,
    }
    resolved: list[PostExtractHookSpec] = []
    for spec in catalog.values():
        if _eval_when(spec.when, ns):
            resolved.append(spec)
    return resolved


def validate_post_extract_catalog() -> list[str]:
    """Return validation errors for post_extract.yaml hooks."""
    errors: list[str] = []
    catalog = load_post_extract_catalog()
    if not catalog:
        errors.append("post_extract.yaml loaded empty or missing")
        return errors
    for hook_id, spec in catalog.items():
        if not spec.module:
            errors.append(f"post_extract {hook_id}: missing module")
            continue
        try:
            get_hook_class(spec)
        except Exception as exc:
            errors.append(f"post_extract {hook_id}: {exc}")
    return errors
