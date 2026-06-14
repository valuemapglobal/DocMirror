# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Character-level column detection strategies (Layer 2 extract)."""

from docmirror.core.extract.char.clustering import detect_columns_by_clustering
from docmirror.core.extract.char.data_voting import detect_columns_by_data_voting
from docmirror.core.extract.char.header_anchors import detect_columns_by_header_anchors
from docmirror.core.extract.char.hline import _extract_by_hline_columns
from docmirror.core.extract.char.projection import detect_columns_by_whitespace_projection
from docmirror.core.extract.char.rect import _extract_by_rect_columns
from docmirror.core.extract.char.word_anchors import detect_columns_by_word_anchors

__all__ = [
    "_extract_by_hline_columns",
    "_extract_by_rect_columns",
    "detect_columns_by_header_anchors",
    "detect_columns_by_whitespace_projection",
    "detect_columns_by_clustering",
    "detect_columns_by_word_anchors",
    "detect_columns_by_data_voting",
]
