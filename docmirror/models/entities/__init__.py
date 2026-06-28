# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Entity domain models — public MOC and DEC exports.

Re-exports the core typed entities used throughout DocMirror:

    ParseResult              Unified parser output contract (MOC)
    DomainExtractionResult   Domain plugin output protocol (DEC)
    BaseResult, Block, PageLayout, Style, TextSpan   Physical layout models

Import from this subpackage for stable public API access without reaching
into individual module files.
"""

from __future__ import annotations

__all__ = [
    "Style",
    "TextSpan",
    "Block",
    "PageLayout",
    "BaseResult",
    "DomainExtractionResult",
    "ParseResult",
]

_LAZY_EXPORTS = {
    "Style": ("docmirror.models.entities.domain", "Style"),
    "TextSpan": ("docmirror.models.entities.domain", "TextSpan"),
    "Block": ("docmirror.models.entities.domain", "Block"),
    "PageLayout": ("docmirror.models.entities.domain", "PageLayout"),
    "BaseResult": ("docmirror.models.entities.domain", "BaseResult"),
    "DomainExtractionResult": ("docmirror.models.entities.domain_result", "DomainExtractionResult"),
    "ParseResult": ("docmirror.models.entities.parse_result", "ParseResult"),
}


def __getattr__(name: str):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    from importlib import import_module

    value = getattr(import_module(module_name), attr)
    globals()[name] = value
    return value
