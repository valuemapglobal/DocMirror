"""Compatibility shim for ``docmirror.topology.resolution``."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

_TARGET = "docmirror.topology.resolution"
__path__ = [str(Path(__file__).resolve().parents[2] / "topology" / "resolution")]


def __getattr__(name: str):
    return getattr(import_module(_TARGET), name)
