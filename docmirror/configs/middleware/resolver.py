# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Middleware pipeline resolver — enhancement profiles + catalog guards.

Resolves the ordered list of middleware names to execute for a given
``content_model`` and ``enhance_mode`` by reading ``enhancement_profiles.yaml``
and applying catalog-level filters.

Resolution steps::

    1. Look up profile for content_model × enhance_mode (fallback to ``standard``)
    2. Flatten v1 flat list or v2 ``stages`` dict in ``GLOBAL_STAGE_ORDER``
    3. Filter by catalog ``enabled``, ``when`` guard eval, and runtime flags
       (``DOCMIRROR_ENABLE_ANOMALY``, ``DOCMIRROR_ENABLE_SLM``)
    4. Topologically sort by ``depends_on`` edges

``when`` guards are Python expressions evaluated against a namespace containing
``result``, ``table_count``, ``document_type``, ``content_model``, and
``enhance_mode``. Guard eval failures default to including the middleware.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from docmirror.configs.format.loader import load_enhancement_profiles, transport_to_content_model

if TYPE_CHECKING:
    from docmirror.models.entities.parse_result import ParseResult

logger = logging.getLogger(__name__)

GLOBAL_STAGE_ORDER: tuple[str, ...] = (
    "NORMALIZE",
    "STRUCTURE",
    "ENRICH",
    "CLASSIFY",
    "CONTEXT",
    "VALIDATE",
)

_RUNTIME_OPTIONAL = frozenset({"AnomalyDetector"})


def _anomaly_detector_enabled() -> bool:
    if os.environ.get("DOCMIRROR_ENABLE_ANOMALY") == "1":
        return True
    return False


def flatten_profile_middleware_names(mode_cfg: list[str] | dict[str, Any]) -> list[str]:
    """Flatten v1 flat list or v2 ``stages`` dict to ordered middleware names."""
    if isinstance(mode_cfg, list):
        return list(mode_cfg)
    if isinstance(mode_cfg, dict):
        stages = mode_cfg.get("stages")
        if isinstance(stages, dict):
            names: list[str] = []
            for stage in GLOBAL_STAGE_ORDER:
                stage_names = stages.get(stage) or []
                if isinstance(stage_names, list):
                    names.extend(str(n) for n in stage_names)
            return names
        return []
    return []


def _profile_names(content_model: str, enhance_mode: str) -> list[str]:
    profiles, _ = load_enhancement_profiles()
    model_cfg = profiles.get(content_model, profiles.get("opaque_binary", {}))
    mode_cfg = model_cfg.get(enhance_mode)
    if mode_cfg is None:
        mode_cfg = model_cfg.get("standard", [])
    return flatten_profile_middleware_names(mode_cfg)


def _eval_when(
    expr: str,
    result: ParseResult | None,
    content_model: str,
    enhance_mode: str,
) -> bool:
    if not expr.strip():
        return True
    if result is None:
        return True
    document_type = getattr(result.entities, "document_type", "") or ""
    ns = {
        "result": result,
        "table_count": result.total_tables,
        "document_type": document_type,
        "content_model": content_model,
        "enhance_mode": enhance_mode,
    }
    try:
        return bool(eval(expr, {"__builtins__": {}}, ns))
    except Exception as exc:
        logger.debug("[MEP] when guard eval failed for %r: %s", expr, exc)
        return True


def _sort_by_depends(names: list[str], catalog: dict) -> list[str]:
    name_set = set(names)
    ordered: list[str] = []
    remaining = list(names)
    while remaining:
        progressed = False
        for name in list(remaining):
            spec = catalog.get(name)
            deps = spec.depends_on if spec else ()
            unmet = [d for d in deps if d in name_set and d not in ordered]
            if not unmet:
                ordered.append(name)
                remaining.remove(name)
                progressed = True
        if not progressed:
            ordered.extend(remaining)
            break
    return ordered


def resolve_pipeline(
    content_model: str,
    enhance_mode: str = "standard",
    result: ParseResult | None = None,
    *,
    file_type: str = "",
) -> list[str]:
    """
    Resolve ordered middleware names for content_model × enhance_mode.

    Applies catalog ``enabled``, ``when`` guards, and dependency ordering.
    """
    model = content_model or transport_to_content_model(file_type)
    names = _profile_names(model, enhance_mode)
    from docmirror.configs.middleware.catalog import load_catalog

    catalog = load_catalog()

    filtered: list[str] = []
    for name in names:
        spec = catalog.get(name)
        if spec is None:
            logger.warning("[MEP] Unknown middleware %r (not in catalog)", name)
            continue
        if not spec.enabled and name not in _RUNTIME_OPTIONAL:
            logger.debug("[MEP] Skipping disabled catalog entry %r", name)
            continue
        if name == "AnomalyDetector" and not _anomaly_detector_enabled():
            logger.debug("[MEP] AnomalyDetector skipped (set DOCMIRROR_ENABLE_ANOMALY=1)")
            continue
        if not _eval_when(spec.when, result, model, enhance_mode):
            logger.debug("[MEP] when guard skipped %r", name)
            continue
        filtered.append(name)

    # SLMEntityExtractor runtime removal in v1.1 — superseded by LlmDocumentRestorer

    resolved = _sort_by_depends(filtered, catalog)

    logger.debug(
        "[MEP] content_model=%s mode=%s → %d middlewares: %s",
        model,
        enhance_mode,
        len(resolved),
        resolved,
    )
    return resolved


def resolve_enhancement_profile(
    content_model: str,
    enhance_mode: str = "standard",
    result: ParseResult | None = None,
) -> list[str]:
    """Backward-compatible alias used by pipeline registry and tests."""
    return resolve_pipeline(content_model, enhance_mode, result)
