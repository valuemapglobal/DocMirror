# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Execution fingerprint for parse-result cache keys.

Combines request-scoped ``ParseControl`` with pipeline/version signals so cache
hits remain valid only when code and upstream config are unchanged.
"""

from __future__ import annotations

import hashlib
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from docmirror.configs.paths import (
    ENHANCEMENT_PROFILES_YAML,
    FORMAT_CAPABILITIES_YAML,
    LAYOUT_PROFILES_YAML,
    MIDDLEWARE_CATALOG_YAML,
    SCENE_KEYWORDS_YAML,
)

if TYPE_CHECKING:
    from docmirror.input.entry.options import ParseControl

logger = logging.getLogger(__name__)

_CONFIG_PATHS: tuple[Path, ...] = (
    MIDDLEWARE_CATALOG_YAML,
    ENHANCEMENT_PROFILES_YAML,
    SCENE_KEYWORDS_YAML,
    FORMAT_CAPABILITIES_YAML,
    LAYOUT_PROFILES_YAML,
)


def _file_content_hash(path: Path) -> str:
    if not path.is_file():
        return "missing"
    try:
        data = path.read_bytes()
        return hashlib.sha256(data).hexdigest()[:12]
    except OSError as exc:
        logger.debug("[ExecutionFingerprint] Cannot read %s: %s", path, exc)
        return "unreadable"


@lru_cache(maxsize=1)
def pipeline_version_fingerprint() -> str:
    """Stable hash of package + pipeline config that affects ParseResult."""
    from docmirror import __version__
    from docmirror.models.mirror.serialization_contract import MIRROR_CONTRACT_VERSION

    components: dict[str, str] = {
        "package": __version__,
        "mirror_contract": MIRROR_CONTRACT_VERSION,
    }
    for path in _CONFIG_PATHS:
        components[path.name] = _file_content_hash(path)
    raw = json.dumps(components, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_execution_fingerprint(parse_control: ParseControl) -> str:
    """Return cache key suffix combining control + pipeline execution identity."""
    payload = {
        "control": parse_control.fingerprint(),
        "pipeline": pipeline_version_fingerprint(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def invalidate_pipeline_fingerprint_cache() -> None:
    """Clear cached pipeline fingerprint (tests / hot reload)."""
    pipeline_version_fingerprint.cache_clear()


__all__ = [
    "build_execution_fingerprint",
    "invalidate_pipeline_fingerprint_cache",
    "pipeline_version_fingerprint",
]
