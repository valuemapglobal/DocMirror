# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Parser Registry — Central registry for parser backends with selection logic.

The ``ParserRegistry`` allows backends to be registered, queried, and
selected by format.  A global singleton is provided for convenience,
but users may create isolated registries for testing or multi-tenant
setups.

Usage::

    from docmirror.input.adapters.parsers import get_registry

    registry = get_registry()
    backend = registry.select("pdf", preference="pymupdf")
    result = await backend.parse("document.pdf")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from docmirror.input.adapters.parsers.protocol import ParserBackend


class ParserRegistry:
    """Registry of available parser backends with selection logic.

    Thread-safe for read operations (``select``, ``list_for_format``).
    Register operations are intended to be performed at startup and
    should be serialised by the caller.
    """

    def __init__(self):
        self._backends: dict[str, ParserBackend] = {}

    # ── Registration ───────────────────────────────────────────────────

    def register(self, backend: ParserBackend) -> None:
        """Register a parser backend.

        Args:
            backend: An object implementing the ``ParserBackend`` protocol.

        Raises:
            TypeError: If *backend* does not satisfy ``ParserBackend``.
            ValueError: If a backend with the same name is already registered.
        """
        from docmirror.input.adapters.parsers.protocol import ParserBackend as PBProtocol

        if not isinstance(backend, PBProtocol):
            raise TypeError(
                f"Backend {backend!r} does not implement ParserBackend protocol. "
                f"Missing attributes or async parse() method."
            )
        name = backend.name
        if name in self._backends:
            raise ValueError(f"Backend {name!r} is already registered")
        self._backends[name] = backend

    # ── Selection ──────────────────────────────────────────────────────

    def select(
        self,
        format: str,
        *,
        preference: str | None = None,
    ) -> ParserBackend:
        """Select the best backend for *format*.

        Selection priority:
        1. If *preference* is given and a backend with that name supports
           *format*, return it.
        2. Return the first registered backend that supports *format*.
        3. If no backend supports *format*, raise ``ValueError``.

        Args:
            format: Target format, e.g. ``"pdf"``, ``"image"``.
            preference: Optional backend name to prefer.

        Returns:
            A ``ParserBackend`` instance.

        Raises:
            ValueError: If no backend supports *format*.
        """
        candidates = self.list_for_format(format)
        if not candidates:
            raise ValueError(f"No parser backend registered for format {format!r}")

        if preference is not None:
            for backend in candidates:
                if backend.name == preference:
                    return backend

        return candidates[0]

    def list_for_format(self, format: str) -> list[ParserBackend]:
        """List all backends that support *format*.

        Args:
            format: Target format string.

        Returns:
            List of matching ``ParserBackend`` instances (ordered by
            registration order).  Empty list if none match.
        """
        return [
            backend
            for backend in self._backends.values()
            if format in backend.supported_formats
        ]

    # ── Queries ────────────────────────────────────────────────────────

    @property
    def available(self) -> dict[str, str]:
        """Backend name → version summary for all registered backends."""
        return {
            name: getattr(backend, "version", "unknown")
            for name, backend in self._backends.items()
        }

    @property
    def names(self) -> list[str]:
        """List of registered backend names."""
        return list(self._backends.keys())

    @property
    def count(self) -> int:
        """Number of registered backends."""
        return len(self._backends)

    def __contains__(self, name: str) -> bool:
        """Check if a backend is registered by name."""
        return name in self._backends

    def __repr__(self) -> str:
        backends = ", ".join(sorted(self._backends))
        return f"<ParserRegistry({backends})>"


# ── Global registry ──────────────────────────────────────────────────────

_registry: ParserRegistry | None = None


def get_registry() -> ParserRegistry:
    """Get or create the global ``ParserRegistry`` singleton."""
    global _registry
    if _registry is None:
        _registry = ParserRegistry()
    return _registry


def register_backend(backend: ParserBackend) -> None:
    """Register a parser backend into the global registry.

    Convenience wrapper around ``get_registry().register(backend)``.
    """
    get_registry().register(backend)


__all__ = [
    "ParserRegistry",
    "get_registry",
    "register_backend",
]
