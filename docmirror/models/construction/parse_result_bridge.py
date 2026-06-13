# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Re-export shim — ParseResultBridge moved to ``core/extraction/bridge.py``.

See ``docs/design/09_models_layer_first_principles_redesign.md`` §4.6 / Appendix C.
"""

from docmirror.core.extraction.bridge import (
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
