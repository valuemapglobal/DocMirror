"""Compatibility shim for ``docmirror.layout.profile``."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

_TARGET = "docmirror.layout.profile"
__path__ = [str(Path(__file__).resolve().parents[2] / "layout" / "profile")]


def __getattr__(name: str):
    return getattr(import_module(_TARGET), name)
