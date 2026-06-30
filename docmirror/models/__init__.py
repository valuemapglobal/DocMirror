# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
DocMirror models package — Mirror Object Contract (MOC) and Domain Extraction Contract (DEC).

This package defines the typed data contracts that flow through the DocMirror
parsing pipeline, from physical layout representation through domain plugin
output to edition JSON serialization.

Architecture layers (see ``docs/design/09_models_layer_first_principles_redesign.md``)::

    entities/       Core MOC types: ``ParseResult``, physical blocks, DEC output
    construction/   Builders converting adapter output to ``ParseResult``
    schemas/        DEC validation schemas per document type
    tracking/       Data lineage via ``Mutation`` records
    edition_serializer   DEC → community/enterprise JSON v2.0
    ehl.py          Evidence/Hypothesis Layer annex helpers
    errors.py       Canonical error codes and failure ``ParseResult`` builders

Public exports: ``ParseResult``, ``DomainExtractionResult``, ``BaseResult``,
``Block``, ``PageLayout``, ``Style``, ``TextSpan``, ``Mutation``.
"""

from __future__ import annotations

__all__ = [
    "Style",
    "TextSpan",
    "Block",
    "PageLayout",
    "BaseResult",
    "Mutation",
    "ParseResult",
    "DomainExtractionResult",
]

_LAZY_EXPORTS = {
    "Style": ("docmirror.models.entities.domain", "Style"),
    "TextSpan": ("docmirror.models.entities.domain", "TextSpan"),
    "Block": ("docmirror.models.entities.domain", "Block"),
    "PageLayout": ("docmirror.models.entities.domain", "PageLayout"),
    "BaseResult": ("docmirror.models.entities.domain", "BaseResult"),
    "Mutation": ("docmirror.models.tracking.mutation", "Mutation"),
    "ParseResult": ("docmirror.models.entities.parse_result", "ParseResult"),
    "DomainExtractionResult": ("docmirror.models.entities.domain_result", "DomainExtractionResult"),
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
