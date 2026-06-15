# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Unified YAML configuration loader for ``docmirror.yaml``.

``YamlConfigLoader`` loads the root runtime config file, expands ``${VAR}`` and
``${VAR:-default}`` environment references recursively, and caches the result
with mtime-based invalidation for hot-reload in long-running processes.

Path resolution priority::

    1. Explicit path passed to ``YamlConfigLoader(path=...)``
    2. ``DOCMIRROR_CONFIG`` environment variable
    3. Package default: ``configs/yaml/docmirror.yaml``

Public helpers::

    config_loader   Module-level singleton ``YamlConfigLoader`` instance
    get_config()    Return the full merged config dict
    resolve_config_path()   Resolve the effective config file path

Dot-path lookups (``config_loader.get("performance.max_page_concurrency")``)
traverse nested dict keys without loading callers into YAML parsing details.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

from docmirror.configs.paths import DOCMIRROR_YAML

logger = logging.getLogger(__name__)

_ENV_REF = re.compile(r"\$\{([^}:]+)(?::-([^}]*))?\}")


def _expand_env(value: Any) -> Any:
    """Expand ``${VAR}`` / ``${VAR:-default}`` in strings recursively."""
    if isinstance(value, str):
        def _repl(match: re.Match) -> str:
            name = match.group(1)
            default = match.group(2)
            env_val = os.getenv(name)
            if env_val is not None and env_val != "":
                return env_val
            return default if default is not None else ""

        return _ENV_REF.sub(_repl, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def resolve_config_path(explicit: Path | str | None = None) -> Path:
    """Resolve docmirror.yaml path (explicit > env > package default)."""
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    env_path = os.getenv("DOCMIRROR_CONFIG", "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    return DOCMIRROR_YAML


class YamlConfigLoader:
    """Load and query docmirror.yaml with mtime-based reload."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = resolve_config_path(path)
        self._data: dict[str, Any] = {}
        self._mtime: float = 0.0

    @property
    def path(self) -> Path:
        return self._path

    def load(self, *, force: bool = False) -> dict[str, Any]:
        if not self._path.is_file():
            if force or not self._data:
                logger.debug("[YamlConfig] No config file at %s — using empty defaults", self._path)
                self._data = {}
                self._mtime = 0.0
            return self._data

        mtime = self._path.stat().st_mtime
        if not force and self._data and mtime == self._mtime:
            return self._data

        try:
            with open(self._path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            if not isinstance(raw, dict):
                raw = {}
            self._data = _expand_env(raw)
            self._mtime = mtime
            logger.debug("[YamlConfig] Loaded %s", self._path)
        except Exception as exc:
            logger.warning("[YamlConfig] Failed to load %s: %s", self._path, exc)
            if not self._data:
                self._data = {}
        return self._data

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Dot-path lookup, e.g. ``performance.max_page_concurrency``."""
        data = self.load()
        node: Any = data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def invalidate(self) -> None:
        self._data = {}
        self._mtime = 0.0


config_loader = YamlConfigLoader()


def get_config() -> dict[str, Any]:
    """Return the full merged config dict."""
    return config_loader.load()
