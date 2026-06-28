# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Pluggable Parser Backend Architecture (GA1.0-ODL-05).

Separates "what format to parse" from "how to parse" by introducing a
``ParserBackend`` protocol and a ``ParserRegistry`` for backend selection.

See :doc:`/docs/design/GA1.0/odl/GA1.0-odl-05-pluggable-parser-backends`
for the design rationale.
"""

from __future__ import annotations

from docmirror.input.adapters.parsers.protocol import (
    ParserBackend,
    ParserCapability,
    RawImage,
    RawKeyValue,
    RawPage,
    RawParseResult,
    RawTable,
    RawText,
)
from docmirror.input.adapters.parsers.registry import (
    ParserRegistry,
    get_registry,
    register_backend,
)

__all__ = [
    "ParserBackend",
    "ParserCapability",
    "ParserRegistry",
    "RawImage",
    "RawKeyValue",
    "RawPage",
    "RawParseResult",
    "RawTable",
    "RawText",
    "get_registry",
    "register_backend",
]
