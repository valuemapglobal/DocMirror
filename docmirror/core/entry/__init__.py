# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Entry package — public exception types for document perception.

Purpose: Exposes ``ExtractionError`` and related entry-layer errors to
callers without importing the full exception hierarchy.

Main components: ``ExtractionError`` (re-exported).

Upstream: ``entry.exceptions``.

Downstream: Application code and ``entry.factory`` error handling.
"""

from docmirror.core.entry.exceptions import ExtractionError
from docmirror.core.entry.options import (
    DocTypeHint,
    OutputControl,
    PageSelection,
    ParseControl,
    ResourceControl,
    normalize_parse_control,
)

__all__ = [
    "DocTypeHint",
    "ExtractionError",
    "OutputControl",
    "PageSelection",
    "ParseControl",
    "ResourceControl",
    "normalize_parse_control",
]
