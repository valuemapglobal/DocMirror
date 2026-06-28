# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Built-in parser backend implementations.

Backends in this package are bundled with DocMirror and registered
automatically at import time via ``register_builtin_backends()``.
"""

from __future__ import annotations

__all__: list[str] = []


def register_builtin_backends() -> int:
    """Register all built-in parser backends into the global registry.

    Called once during DocMirror startup (e.g. in ``docmirror/__init__.py``
    or at adapter import time).

    Returns:
        Number of backends registered.
    """
    from docmirror.input.adapters.parsers.registry import get_registry

    registry = get_registry()
    count = 0

    # PyMuPDF (always available when docmirror is installed)
    try:
        from docmirror.input.adapters.parsers.backends.pymupdf import PyMuPDFBackend

        registry.register(PyMuPDFBackend())
        count += 1
    except ImportError:
        pass

    return count
