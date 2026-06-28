"""Compatibility shim for ``docmirror.topology.relations``."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

_TARGET = "docmirror.topology.relations"
__path__ = [str(Path(__file__).resolve().parents[2] / "topology" / "relations")]


def __getattr__(name: str):
    return getattr(import_module(_TARGET), name)
