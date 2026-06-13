# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Re-export shim — physical models live in ``core/internal/physical.py``.

See ``docs/design/09_models_layer_first_principles_redesign.md`` §4.6.
"""

from docmirror.core.internal.physical import (
    BaseResult,
    Block,
    PageLayout,
    Style,
    TextSpan,
)

__all__ = ["Style", "TextSpan", "Block", "PageLayout", "BaseResult"]
