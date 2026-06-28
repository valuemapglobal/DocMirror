"""Compatibility shim for ``docmirror.topology.region_graph``."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

_TARGET = "docmirror.topology.region_graph"
__path__ = [str(Path(__file__).resolve().parents[2] / "topology" / "region_graph")]


def __getattr__(name: str):
    return getattr(import_module(_TARGET), name)
