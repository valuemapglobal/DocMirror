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

from docmirror.input.entry.exceptions import ExtractionError
from docmirror.input.entry.options import (
    DocTypeHint,
    PageSelection,
    ParsePolicy,
    normalize_parse_policy,
)

__all__ = [
    "DocTypeHint",
    "ExtractionError",
    "PageSelection",
    "ParsePolicy",
    "normalize_parse_policy",
]
