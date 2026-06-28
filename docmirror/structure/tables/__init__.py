"""Compatibility shim for ``docmirror.tables``."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

_TARGET = "docmirror.tables"
__path__ = [str(Path(__file__).resolve().parents[2] / "tables")]


def __getattr__(name: str):
    return getattr(import_module(_TARGET), name)
