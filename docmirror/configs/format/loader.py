# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Load format_capabilities.yaml and enhancement_profiles.yaml."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import yaml

from docmirror.configs.format.models import (
    ExtractionBinding,
    FallbackSpec,
    FormatCapability,
    TranscodeSpec,
)
from docmirror.configs.paths import ENHANCEMENT_PROFILES_YAML, FORMAT_CAPABILITIES_YAML

logger = logging.getLogger(__name__)


def _parse_transcode(raw: dict[str, Any] | None) -> TranscodeSpec | None:
    if not raw:
        return None
    return TranscodeSpec(
        tool=str(raw.get("tool", "libreoffice")),
        target=str(raw.get("target", "pdf")),
        on_missing=str(raw.get("on_missing", "FORMAT_REQUIRES_CONVERTER")),
    )


def _parse_binding(raw: dict[str, Any] | None) -> ExtractionBinding | None:
    if not raw:
        return None
    fb_raw = raw.get("fallback")
    fallback = None
    if isinstance(fb_raw, dict):
        fallback = FallbackSpec(
            adapter=str(fb_raw["adapter"]),
            when=str(fb_raw.get("when", "primary_empty")),
        )
    return ExtractionBinding(
        adapter=raw.get("adapter"),
        transcode=_parse_transcode(raw.get("transcode")),
        fallback=fallback,
        deserializer=raw.get("deserializer"),
        kwargs=dict(raw.get("kwargs") or {}),
    )


def _parse_capability(raw: dict[str, Any]) -> FormatCapability:
    exts = frozenset(str(e).lower() for e in (raw.get("extensions") or []))
    mimes = frozenset(str(m).lower() for m in (raw.get("mime") or []))
    return FormatCapability(
        id=str(raw["id"]),
        transport=str(raw["transport"]),
        content_model=str(raw["content_model"]),
        status=str(raw.get("status", "unsupported")),  # type: ignore[arg-type]
        extensions=exts,
        mime=mimes,
        mime_prefix=str(raw.get("mime_prefix") or ""),
        binding=_parse_binding(raw.get("binding")),
    )


@lru_cache(maxsize=1)
def load_format_registry() -> tuple[dict[str, FormatCapability], dict[str, str], dict[str, str]]:
    """
    Returns:
        capabilities_by_id, extension_map (ext -> cap_id), mime_map (mime -> cap_id)
    """
    path = FORMAT_CAPABILITIES_YAML
    if not path.is_file():
        logger.warning("[FCR] Missing %s", path)
        return {}, {}, {}

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    caps: dict[str, FormatCapability] = {}
    ext_map: dict[str, str] = {}
    mime_map: dict[str, str] = {}

    for cap_id, mime in (data.get("mime_map") or {}).items():
        mime_map[str(mime).lower()] = str(cap_id)

    for raw in data.get("capabilities") or []:
        cap = _parse_capability(raw)
        caps[cap.id] = cap
        for ext in cap.extensions:
            ext_map[ext] = cap.id
        for mime in cap.mime:
            mime_map[mime] = cap.id

    return caps, ext_map, mime_map


def invalidate_format_cache() -> None:
    load_format_registry.cache_clear()
    load_enhancement_profiles.cache_clear()


@lru_cache(maxsize=1)
def load_enhancement_profiles() -> tuple[dict[str, dict[str, list[str]]], dict[str, str]]:
    """Returns (profiles, transport_fallback)."""
    path = ENHANCEMENT_PROFILES_YAML
    if not path.is_file():
        return {}, {}

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    profiles = {
        str(k): {str(mode): list(mws) for mode, mws in v.items()}
        for k, v in (data.get("profiles") or {}).items()
    }
    transport_fallback = {str(k): str(v) for k, v in (data.get("transport_fallback") or {}).items()}
    return profiles, transport_fallback
