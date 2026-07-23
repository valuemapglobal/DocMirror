# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Post-extract hook catalog loader (PEC layer).

Merges the generic ``configs/yaml/post_extract.yaml`` catalog with plugin-owned
``post_extract`` resources into ``PostExtractHookSpec`` records,
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
from importlib.resources import files
from pathlib import PurePosixPath
from typing import Any

import yaml

from docmirror.configs.paths import POST_EXTRACT_YAML

logger = logging.getLogger(__name__)
_catalog_cache: dict[str, PostExtractHookSpec] | None = None
_catalog_signature: int | None = None


@dataclass(frozen=True)
class PostExtractHookSpec:
    hook_id: str
    module: str
    class_name: str
    when: str = ""
    mutates_facts: bool = False
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
    global _catalog_cache, _catalog_signature  # noqa: PLW0603

    payloads, signature = _catalog_payloads()
    if _catalog_cache is not None and signature == _catalog_signature:
        return _catalog_cache
    _catalog_signature = signature

    catalog: dict[str, PostExtractHookSpec] = {}
    for data in payloads:
        for hook_id, raw in (data.get("hooks") or {}).items():
            if not isinstance(raw, dict):
                continue
            catalog[str(hook_id)] = PostExtractHookSpec(
                hook_id=str(hook_id),
                module=str(raw.get("module", "")),
                class_name=str(raw.get("class", hook_id)),
                when=str(raw.get("when") or ""),
                mutates_facts=bool(raw.get("mutates_facts", False)),
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


def _catalog_payloads() -> tuple[list[dict[str, Any]], int]:
    texts: list[str] = []
    if POST_EXTRACT_YAML.is_file():
        texts.append(POST_EXTRACT_YAML.read_text(encoding="utf-8"))
    plugin_root = files("docmirror").joinpath("plugins")
    # The generic provider is the fallback/finalizer and therefore contributes
    # hooks after every concrete provider.
    for plugin_dir in sorted(plugin_root.iterdir(), key=lambda item: (item.name == "generic", item.name)):
        manifest_path = plugin_dir.joinpath("plugin.yaml")
        if not plugin_dir.is_dir() or not manifest_path.is_file():
            continue
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        relative_text = str(((manifest.get("resources") or {}).get("post_extract")) or "").strip()
        relative_path = PurePosixPath(relative_text)
        if not relative_text or relative_path.is_absolute() or ".." in relative_path.parts:
            continue
        resource_path = plugin_dir.joinpath(*relative_path.parts)
        if resource_path.is_file():
            texts.append(resource_path.read_text(encoding="utf-8"))
    payloads = [payload for text in texts if isinstance((payload := yaml.safe_load(text) or {}), dict)]
    return payloads, hash(tuple(texts))


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
