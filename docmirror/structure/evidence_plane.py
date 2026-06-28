"""Compatibility shim for ``docmirror.evidence.plane``."""

from __future__ import annotations

from docmirror.evidence.plane import *  # noqa: F403
from docmirror.evidence.plane import _finalize_indexes

__all__ = [name for name in globals() if not name.startswith("__")]
