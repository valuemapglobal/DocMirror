# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
DocMirror Service Container
============================

Lazy singleton registry for core framework services.

This is **not** on the primary user path — callers should prefer
``perceive_document()`` from ``docmirror.input.pipeline``.  The container
exists so tests and extensions can obtain shared ``ParserDispatcher`` /
``Orchestrator`` instances without duplicating singleton logic.

Managed services:
    - ``settings``     → ``DocMirrorSettings`` (env-backed config)
    - ``dispatcher``   → ``ParserDispatcher`` (L0 file routing)
    - ``orchestrator`` → ``Orchestrator`` (middleware pipeline)

Not managed here:
    - Parse-result cache (``framework/cache.py``) — optional, not wired into
      the default pipeline; import ``parse_cache`` directly if re-enabled.

Usage::

    from docmirror.framework.di import get_dispatcher, get_orchestrator

    dispatcher = get_dispatcher()
    orchestrator = get_orchestrator()
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from docmirror.configs.runtime.settings import DocMirrorSettings
    from docmirror.framework.dispatcher import ParserDispatcher
    from docmirror.framework.orchestrator import Orchestrator


class DocMirrorContainer:
    """
    Thread-safe lazy singleton container for framework services.

    One global instance (``container``) is shared across the process.
    ``reset()`` clears all cached instances (for tests).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._settings: DocMirrorSettings | None = None
        self._orchestrator: Orchestrator | None = None
        self._dispatcher: ParserDispatcher | None = None

    @property
    def settings(self) -> DocMirrorSettings:
        """Global settings singleton (from environment)."""
        if self._settings is None:
            with self._lock:
                if self._settings is None:
                    from docmirror.configs.runtime.settings import DocMirrorSettings

                    self._settings = DocMirrorSettings.from_env()
                    logger.info("[DI Container] Initialized DocMirrorSettings")
        return self._settings

    @property
    def orchestrator(self) -> Orchestrator:
        """Shared Orchestrator for middleware enrichment."""
        if self._orchestrator is None:
            with self._lock:
                if self._orchestrator is None:
                    from docmirror.framework.orchestrator import Orchestrator

                    self._orchestrator = Orchestrator(
                        settings=self.settings,
                        config=self.settings.to_dict(),
                    )
                    logger.info("[DI Container] Initialized Orchestrator")
        return self._orchestrator

    @property
    def dispatcher(self) -> ParserDispatcher:
        """Shared ParserDispatcher for L0 routing."""
        if self._dispatcher is None:
            with self._lock:
                if self._dispatcher is None:
                    from docmirror.framework.dispatcher import ParserDispatcher

                    self._dispatcher = ParserDispatcher()
                    logger.info("[DI Container] Initialized ParserDispatcher")
        return self._dispatcher

    def reset(self) -> None:
        """Drop all cached instances (for tests)."""
        with self._lock:
            self._settings = None
            self._orchestrator = None
            self._dispatcher = None
        logger.info("[DI Container] Reset all instances")


# Global container — single source of truth for framework singletons
container = DocMirrorContainer()


def get_settings() -> DocMirrorSettings:
    """Return the global ``DocMirrorSettings`` singleton."""
    return container.settings


def get_orchestrator() -> Orchestrator:
    """Return the global ``Orchestrator`` singleton."""
    return container.orchestrator


def get_dispatcher() -> ParserDispatcher:
    """Return the global ``ParserDispatcher`` singleton."""
    return container.dispatcher


def reset_container() -> None:
    """Reset all container singletons (for tests)."""
    container.reset()
