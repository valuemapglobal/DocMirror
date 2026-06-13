# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Middleware Registry - Auto-Discovery Pattern
=============================================

Provides automatic middleware registration using decorators.

Benefits:
    - Zero configuration: Add middleware by adding decorator
    - Type safety: Validates middleware class at registration
    - Early error detection: Duplicate registration fails immediately
    - Order control: Optional order parameter for pipeline sequencing

Usage::

    from docmirror.middlewares.registry import register_middleware

    @register_middleware("SceneDetector", order=1)
    class SceneDetector(BaseMiddleware):
        pass
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Type

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from docmirror.middlewares.base import BaseMiddleware


class MiddlewareRegistry:
    """
    Middleware registration and discovery system.

    Uses decorator pattern for automatic registration at class definition time.
    """

    _registry: dict[str, type[BaseMiddleware]] = {}
    _load_order: list[str] = []

    @classmethod
    def register(cls, name: str, order: int = 0):
        """
        Decorator to register a middleware class.

        Args:
            name: Unique middleware name (e.g., "SceneDetector")
            order: Optional order for pipeline sequencing (lower = earlier)

        Returns:
            Decorator function

        Raises:
            ValueError: If middleware name already registered

        Example::

            @register_middleware("SceneDetector", order=1)
            class SceneDetector(BaseMiddleware):
                pass
        """

        def decorator(mw_class: type[BaseMiddleware]) -> type[BaseMiddleware]:
            # Validate
            if name in cls._registry:
                raise ValueError(
                    f"Middleware '{name}' already registered. Existing: {cls._registry[name]}, Attempting: {mw_class}"
                )

            # Check base class
            from docmirror.middlewares.base import BaseMiddleware

            if not issubclass(mw_class, BaseMiddleware):
                raise TypeError(f"Middleware '{name}' must inherit from BaseMiddleware, got {mw_class}")

            # Register
            cls._registry[name] = mw_class
            cls._load_order.append(name)

            logger.debug(f"[MiddlewareRegistry] Registered '{name}' (order={order})")

            return mw_class

        return decorator

    @classmethod
    def get(cls, name: str) -> type[BaseMiddleware]:
        """
        Get middleware class by name.

        Args:
            name: Middleware name

        Returns:
            Middleware class

        Raises:
            KeyError: If middleware not found
        """
        mw_class = cls._registry.get(name)
        if mw_class is None:
            available = ", ".join(sorted(cls._registry.keys()))
            raise KeyError(f"Middleware '{name}' not found. Available: {available}")
        return mw_class

    @classmethod
    def list_all(cls) -> list[str]:
        """List all registered middleware names."""
        return list(cls._registry.keys())

    @classmethod
    def list_with_order(cls) -> list[tuple[str, type[BaseMiddleware]]]:
        """List all middlewares with their classes."""
        return [(name, cls._registry[name]) for name in cls._load_order]

    @classmethod
    def has(cls, name: str) -> bool:
        """Check if middleware is registered."""
        return name in cls._registry

    @classmethod
    def build_pipeline(cls, names: list[str], config: dict = None) -> list[BaseMiddleware]:
        """
        Build middleware pipeline from names.

        Args:
            names: List of middleware names in execution order
            config: Optional configuration dict for all middlewares

        Returns:
            List of middleware instances
        """
        if config is None:
            config = {}

        middlewares = []
        for name in names:
            mw_class = cls.get(name)
            mw_config = config.get(name, {})
            middlewares.append(mw_class(config=mw_config))

        return middlewares

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations (for testing)."""
        cls._registry.clear()
        cls._load_order.clear()
        logger.info("[MiddlewareRegistry] Cleared all registrations")


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience Function
# ═══════════════════════════════════════════════════════════════════════════════


def register_middleware(name: str, order: int = 0):
    """
    Decorator to register a middleware class.

    Args:
        name: Unique middleware name
        order: Optional order for pipeline sequencing

    Example::

        @register_middleware("SceneDetector", order=1)
        class SceneDetector(BaseMiddleware):
            pass
    """
    return MiddlewareRegistry.register(name, order)
