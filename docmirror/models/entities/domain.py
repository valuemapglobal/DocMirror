# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Physical layout model re-export shim.

Canonical implementations live in ``docmirror.models.entities.physical``. This
module re-exports them at the models layer boundary so callers following
design 09 §4.6 import physical types from ``docmirror.models.entities.domain``
without depending on the core package path directly.

Exports: ``Style``, ``TextSpan``, ``Block``, ``PageLayout``, ``BaseResult``.
"""

from docmirror.models.entities.physical import (
    BaseResult,
    Block,
    PageLayout,
    Style,
    TextSpan,
)

__all__ = ["Style", "TextSpan", "Block", "PageLayout", "BaseResult"]
