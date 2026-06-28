"""Compatibility shim for ``docmirror.geometry.verification``."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

_TARGET = "docmirror.geometry.verification"
__path__ = [str(Path(__file__).resolve().parents[2] / "geometry" / "verification")]


def __getattr__(name: str):
    return getattr(import_module(_TARGET), name)
