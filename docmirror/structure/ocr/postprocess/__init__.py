# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
OCR postprocess subpackage — context-aware OCR correction.

Purpose: Hosts generic and column-aware postprocessors applied after raw OCR.

Main components: ``ContextAwareOCRPostProcessor``, generic postprocess hooks.

Upstream: Raw OCR tokens with layout context.

Downstream: Final cell text in ``table.pipeline`` and blocks.
"""

from .column_aware import ColumnConstraints, ContextAwareOCRPostProcessor

__all__ = ["ColumnConstraints", "ContextAwareOCRPostProcessor"]
