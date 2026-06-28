"""Compatibility shim for ``docmirror.layout.segment``.

New imports should use ``docmirror.layout.segment``. This package redirects
legacy submodule imports during the 1.1 migration window.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

_TARGET = "docmirror.layout.segment"
__path__ = [str(Path(__file__).resolve().parents[2] / "layout" / "segment")]


def __getattr__(name: str):
    return getattr(import_module(_TARGET), name)
