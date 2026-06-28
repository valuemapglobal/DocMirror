# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Filter flow texts via page line ownership SSOT (Design 19 axiom A — P0)."""

from __future__ import annotations

from typing import Any

from docmirror.structure.ocr.page_canvas.models import PageRegion
from docmirror.structure.ocr.page_canvas.page_token_ownership import filter_flow_by_ownership


def filter_flow_texts_not_in_regions(
    texts: list[dict[str, Any]],
    regions: list[PageRegion],
) -> list[dict[str, Any]]:
    """Return flow texts = complement of lines owned by region structure."""
    return filter_flow_by_ownership(texts, regions)
