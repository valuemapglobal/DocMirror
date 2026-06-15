# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Extract package — table and structured content extraction strategies.

Purpose: Layered table extraction engines, char-level column detection, and
profile-aware strategy selection for ``data_table`` zones.

Main components: ``extract_tables_layered``, char strategies, ``RapidTableEngine``.

Upstream: ``pipeline.handlers.table_zone``, ``segment`` zone crops.

Downstream: ``extraction.table_postprocessor``, ``table.pipeline``.
"""

from docmirror.core.extract.engine import extract_tables_layered
from docmirror.core.extract.classifier import get_last_layer_timings

__all__ = ["extract_tables_layered", "get_last_layer_timings"]
