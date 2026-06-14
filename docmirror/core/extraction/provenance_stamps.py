# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Stable evidence_ids for mirror blocks missing extractor-level provenance."""

from __future__ import annotations

from docmirror.eval.metrics import evidence_fingerprint
from docmirror.models.entities.parse_result import ParseResult


def stamp_mirror_block_provenance(result: ParseResult) -> int:
    """Assign fallback evidence_ids to texts/tables that lack them.

    Returns the number of blocks stamped.
    """
    stamped = 0
    for page in result.pages:
        for idx, text in enumerate(page.texts):
            if text.evidence_ids:
                continue
            fp = evidence_fingerprint(text.content)
            suffix = f"_{fp}" if fp else ""
            text.evidence_ids = [f"mirror_txt_p{page.page_number}_{idx}{suffix}"]
            stamped += 1
        for table in page.tables:
            if table.evidence_ids:
                continue
            tid = table.table_id or f"mirror_tbl_p{page.page_number}"
            table.evidence_ids = [tid]
            stamped += 1
    return stamped
