# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Backend Discovery — Find installed parser backends via entry points.

Uses ``importlib.metadata.entry_points`` to discover backends that
declare the ``docmirror.parsers`` entry-point group in their
``pyproject.toml`` (or ``setup.cfg`` / ``setup.py``).

Usage::

    from docmirror.input.adapters.parsers.discovery import discover_backends

    backends = discover_backends()
    for name, backend in backends.items():
        print(f"Found {name} (version={backend.version})")

Distribution authors register their backends like this::

    # pyproject.toml
    [project.entry-points."docmirror.parsers"]
    my_parser = "mypackage.module:MyParserClass"
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docmirror.input.adapters.parsers.protocol import ParserBackend


def discover_backends() -> dict[str, ParserBackend]:
    """Discover installed parser backends via entry points.

    Scans the ``docmirror.parsers`` entry-point group and instantiates
    each registered backend class.

    Returns:
        Dict mapping backend name → ``ParserBackend`` instance for each
        successfully discovered and instantiated backend.
    """
    backends: dict[str, ParserBackend] = {}

    try:
        from importlib.metadata import entry_points

        eps = entry_points(group="docmirror.parsers")
    except (ImportError, TypeError):
        # Python <3.9 fallback / edge case
        return backends

    for ep in eps:
        try:
            backend_cls = ep.load()
            backend = backend_cls()
            backends[backend.name] = backend
        except Exception as exc:
            # Log and skip — a broken third-party backend should not
            # prevent the rest of the system from starting.
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                "Failed to load parser backend %r: %s",
                ep.value,
                exc,
            )

    return backends


def register_discovered_backends() -> int:
    """Discover and register all backends into the global registry.

    Convenience for startup: discovers backends and registers each one
    into ``docmirror.input.adapters.parsers.get_registry()``.

    Returns:
        Number of backends successfully registered.
    """
    from docmirror.input.adapters.parsers.registry import get_registry

    registry = get_registry()
    backends = discover_backends()
    count = 0
    for backend in backends.values():
        try:
            registry.register(backend)
            count += 1
        except (TypeError, ValueError):
            import logging

            logger = logging.getLogger(__name__)
            logger.exception("Failed to register backend %r", backend.name)
    return count


__all__ = [
    "discover_backends",
    "register_discovered_backends",
]
