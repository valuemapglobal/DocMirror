# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Table extraction engine (CPA extract stage)."""

from docmirror.core.extract.engine import extract_tables_layered
from docmirror.core.extract.classifier import get_last_layer_timings

__all__ = ["extract_tables_layered", "get_last_layer_timings"]
