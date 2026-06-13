# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Resolve file path + MIME to FormatCapability."""

from __future__ import annotations

import logging
from pathlib import Path

from docmirror.configs.format.loader import load_format_registry
from docmirror.configs.format.models import UNKNOWN_CAPABILITY, FormatCapability

logger = logging.getLogger(__name__)


def _extension_candidates(path: Path) -> list[str]:
    """Return normalized suffixes longest-first (e.g. .tar.gz before .gz)."""
    name = path.name.lower()
    if "." not in name or name.startswith("."):
        single = path.suffix.lower()
        return [single] if single else []

    parts = name.split(".")
    suffixes = ["." + ".".join(parts[i:]) for i in range(1, len(parts))]
    suffixes.sort(key=len, reverse=True)
    return suffixes


def resolve_capability(path: Path, known_mime: str = "") -> FormatCapability:
    """
    Resolve format capability for a file.

    Priority: exact MIME → MIME prefix (image/*) → longest extension match → unknown.
    """
    caps, ext_map, mime_map = load_format_registry()
    if not caps:
        return UNKNOWN_CAPABILITY

    mime = (known_mime or "").lower().strip()
    cap_id: str | None = None

    if mime:
        cap_id = mime_map.get(mime)
        if cap_id is None:
            for cid, cap in caps.items():
                if cap.mime_prefix and mime.startswith(cap.mime_prefix):
                    cap_id = cid
                    break

    if cap_id is None:
        for suffix in _extension_candidates(path):
            cap_id = ext_map.get(suffix)
            if cap_id is not None:
                break

    if cap_id is None:
        return UNKNOWN_CAPABILITY

    return caps.get(cap_id, UNKNOWN_CAPABILITY)


def detect_transport(path: Path, known_mime: str = "") -> str:
    """Return transport string for a path (backward-compatible with detect_file_type)."""
    return resolve_capability(path, known_mime).transport


def get_capability_by_transport(transport: str) -> FormatCapability | None:
    """First supported capability for a transport (used by get_parser fallback)."""
    caps, _, _ = load_format_registry()
    for cap in caps.values():
        if cap.transport == transport and cap.status == "supported" and cap.binding:
            return cap
    return None
