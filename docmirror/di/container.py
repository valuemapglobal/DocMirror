# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
DocMirror Dependency Injection Container
=========================================

Centralized dependency management using the dependency-injector library.

Benefits:
    - Eliminates circular imports
    - Makes dependencies explicit and testable
    - Provides single point of configuration
    - Supports lazy loading and singleton patterns

Usage::

    from docmirror.di.container import container

    # Get instances
    dispatcher = container.dispatcher()
    orchestrator = container.orchestrator()
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from docmirror.configs.settings import DocMirrorSettings
    from docmirror.framework.cache import ParseCache
    from docmirror.framework.dispatcher import ParserDispatcher
    from docmirror.framework.orchestrator import Orchestrator


# ═══════════════════════════════════════════════════════════════════════════════
# Container Implementation (Lazy Loading Pattern)
# ═══════════════════════════════════════════════════════════════════════════════


class DocMirrorContainer:
    """
    Dependency injection container for DocMirror.

    Manages all service lifecycles and dependencies.
    Uses lazy initialization to avoid circular imports.
    """

    def __init__(self):
        self._instances = {}
        self._settings = None
        self._cache = None
        self._orchestrator = None
        self._dispatcher = None

    @property
    def settings(self) -> DocMirrorSettings:
        """Get or create settings singleton."""
        if self._settings is None:
            from docmirror.configs.settings import DocMirrorSettings

            self._settings = DocMirrorSettings.from_env()
            logger.info("[DI Container] Initialized DocMirrorSettings")
        return self._settings

    @property
    def cache(self) -> ParseCache:
        """Get or create cache singleton."""
        if self._cache is None:
            from docmirror.framework.cache import ParseCache

            self._cache = ParseCache()
            logger.info("[DI Container] Initialized ParseCache")
        return self._cache

    @property
    def orchestrator(self) -> Orchestrator:
        """Get or create orchestrator instance."""
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
        """Get or create dispatcher singleton."""
        if self._dispatcher is None:
            from docmirror.framework.dispatcher import ParserDispatcher

            self._dispatcher = ParserDispatcher()
            logger.info("[DI Container] Initialized ParserDispatcher")
        return self._dispatcher

    def reset(self) -> None:
        """Reset all instances (for testing)."""
        self._instances.clear()
        self._settings = None
        self._cache = None
        self._orchestrator = None
        self._dispatcher = None
        logger.info("[DI Container] Reset all instances")


# ═══════════════════════════════════════════════════════════════════════════════
# Global Container Instance
# ═══════════════════════════════════════════════════════════════════════════════

container = DocMirrorContainer()


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience Functions (Backward Compatibility)
# ═══════════════════════════════════════════════════════════════════════════════


def get_settings() -> DocMirrorSettings:
    """Get global settings instance."""
    return container.settings


def get_cache() -> ParseCache:
    """Get global cache instance."""
    return container.cache


def get_orchestrator() -> Orchestrator:
    """Get global orchestrator instance."""
    return container.orchestrator


def get_dispatcher() -> ParserDispatcher:
    """Get global dispatcher instance."""
    return container.dispatcher


def reset_container() -> None:
    """Reset container (for testing)."""
    container.reset()
