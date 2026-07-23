# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Normalize TQG inputs through the production sealed Mirror projector."""

from __future__ import annotations

from typing import Any

from docmirror.models.entities.parse_result import ParseResult
from docmirror.models.sealed import SealedParseResult, seal_parse_result
from docmirror.output.mirror_projector import project_mirror


def mirror_api(value: Any, **projection_options: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, (ParseResult, SealedParseResult)):
        return project_mirror(seal_parse_result(value), **projection_options)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    return {}


__all__ = ["mirror_api"]
