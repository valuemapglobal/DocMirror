# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Geometry helpers for Mirror physical layout conservation."""

from docmirror.core.geometry.bbox import (
    area,
    center,
    contains,
    intersection,
    iou,
    normalize,
    union,
)
from docmirror.core.geometry.models import EvidenceToken
from docmirror.core.geometry.table_attrs import build_table_geometry_attrs, table_geometry_coverage
from docmirror.core.geometry.table_geometry import build_table_geometry

__all__ = [
    "area",
    "center",
    "contains",
    "intersection",
    "iou",
    "normalize",
    "union",
    "EvidenceToken",
    "build_table_geometry_attrs",
    "build_table_geometry",
    "table_geometry_coverage",
]
