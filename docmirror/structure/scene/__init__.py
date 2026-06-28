"""Compatibility shim for ``docmirror.layout.scene``."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

_TARGET = "docmirror.layout.scene"
__path__ = [str(Path(__file__).resolve().parents[2] / "layout" / "scene")]


def __getattr__(name: str):
    return getattr(import_module(_TARGET), name)
