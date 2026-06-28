# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Credit-report supplemental local structure detection (legacy — P4).

Prefer ``page_segment.detect_pre_grid_field_supplements`` (registered by default).
Enable this module only with ``DOCMIRROR_PCM_LEGACY_SUPPLEMENT=1``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from docmirror.ocr.local_structure.candidate_supplement import register_local_structure_supplement
from docmirror.ocr.local_structure.models import LocalStructureCandidate
from docmirror.ocr.local_structure.utils import union_bbox
from docmirror.ocr.micro_grid.models import OCRToken

_REPAYMENT_ANCHOR_RE = re.compile(r"还款记录")
_CLOSED_MARKERS = re.compile(r"结[清消]|账户关闭|关闭日期")
_NUMBERED_ACCOUNT_RE = re.compile(r"账户\s*\d+")


@register_local_structure_supplement
def detect_credit_closed_account_blocks(
    items: list[dict[str, Any]],
    *,
    tokens: Iterable[OCRToken] | None = None,
    page: int,
    page_width: float | None = None,
    page_height: float | None = None,
    existing: Iterable[LocalStructureCandidate] | None = None,
) -> list[LocalStructureCandidate]:
    """Detect account-1 style closed-loan blocks immediately above repayment grids."""
    del tokens
    del page_width
    del page_height
    del existing
    if not items:
        return []

    repayment_idx = next(
        (idx for idx, line in enumerate(items) if _REPAYMENT_ANCHOR_RE.search(line["text"])),
        None,
    )
    if repayment_idx is None or repayment_idx < 2:
        return []

    close_idx = None
    for idx in range(repayment_idx - 1, -1, -1):
        if _CLOSED_MARKERS.search(items[idx]["text"]):
            close_idx = idx
            break
    if close_idx is None:
        return []

    start_idx = close_idx
    for idx in range(close_idx - 1, max(-1, close_idx - 12), -1):
        gap = items[idx + 1]["bbox"][1] - items[idx]["bbox"][3]
        if gap > 45.0:
            start_idx = idx + 1
            break
        start_idx = idx

    block = items[start_idx:repayment_idx]
    if len(block) < 2:
        return []
    if any(_NUMBERED_ACCOUNT_RE.search(line["text"]) for line in block[:2]):
        return []

    return [
        LocalStructureCandidate(
            candidate_id=f"lscredit_p{page}_closed0",
            page=page,
            bbox=union_bbox(line["bbox"] for line in block),
            anchors=("账户1",),
            reason_codes=("credit_closed_account_block", "pre_repayment_block"),
            score=0.88,
            source_line_ids=tuple(line["line_id"] for line in block),
        )
    ]
