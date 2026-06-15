# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
ParseResultBridge re-export shim — legacy-to-MOC construction bridge.

Canonical implementation lives in ``docmirror.core.bridge.parse_result_bridge``.
This module re-exports ``ParseResultBridge`` and internal helpers at the models
layer boundary per design 09 §4.6 / Appendix C.

``ParseResultBridge`` converts adapter and legacy parser outputs into typed
``ParseResult`` instances, composing logical tables from blocks and inferring
cell values from physical evidence.
"""

from docmirror.core.bridge.parse_result_bridge import (
    ParseResultBridge,
    _blocks_to_pages,
    _compose_logical_tables,
    _infer_cell_value,
)

__all__ = [
    "ParseResultBridge",
    "_blocks_to_pages",
    "_compose_logical_tables",
    "_infer_cell_value",
]
