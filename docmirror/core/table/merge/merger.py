# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Table merger — cross-page physical table merge.

Purpose: Groups continuation tables across pages, merges rows, and quarantines
column-mismatched fragments with logging.

Main components: ``merge_cross_page_tables``, ``collect_cross_page_merge_groups``.

Upstream: Per-page physical tables, ``table.cross_page_predictor``.

Downstream: ``table.compose.composer``, ``bridge.parse_result_bridge``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from docmirror.models.entities.domain import Block, PageLayout
from docmirror.core.utils.text_utils import headers_match
from docmirror.core.utils.vocabulary import _is_header_row
from docmirror.core.table.pipeline.stage_preamble import _strip_preamble

logger = logging.getLogger(__name__)

_QUARANTINE_MERGE_ACTIONS = frozenset({"quarantine_col_mismatch", "quarantine_fragment"})
_QUARANTINE_ACTIONS = {
    "quarantine_col_mismatch": "col_count_mismatch",
    "quarantine_fragment": "fragment_table",
}


def is_quarantined_merge_group(group: dict) -> bool:
    """True when merge planning marked this group as physical quarantine."""
    for entry in group.get("merge_log") or []:
        if entry.get("action") in _QUARANTINE_MERGE_ACTIONS:
            return True
    return False


def _median_col_count(rows: list) -> int:
    """P3-6: Compute the median column count of a table's rows."""
    if not rows:
        return 0
    counts = sorted(len(r) for r in rows if isinstance(r, (list, tuple)))
    if not counts:
        return 0
    return counts[len(counts) // 2]


def _profile_quarantines_standalone(profile: Any | None) -> bool:
    """Borderless ledger profiles quarantine non-mergeable tail pages (E8 / design-06)."""
    if profile is None:
        return False
    return bool(
        getattr(profile, "merge_quarantine_on_col_mismatch", False)
        and getattr(profile, "is_borderless_ledger", lambda: False)()
    )


def _profile_quarantines_fragments(profile: Any | None) -> bool:
    """Bank-statement profiles: quarantine fragment tables at merge planning (LTQG input)."""
    if profile is None:
        return False
    hint = getattr(profile, "document_type_hint", None) or ""
    if hint == "bank_statement":
        return True
    pid = getattr(profile, "profile_id", "") or ""
    return pid == "borderless_ledger_bank"


def _looks_like_fragment_table(rows: list) -> bool:
    """Heuristic: many rows but no ledger header / almost no date-amount data."""
    if not rows or len(rows) < 8:
        return False
    from docmirror.core.utils.vocabulary import _RE_IS_AMOUNT, _RE_IS_DATE, _score_header_by_vocabulary

    header_cells = [str(c or "") for c in (rows[0] if rows else [])]
    header_score = _score_header_by_vocabulary(header_cells, categories=["BANK_STATEMENT"])
    if header_score >= 2:
        return False
    body = rows[1:] if len(rows) > 1 else list(rows)
    if not body:
        return True

    def _strong_data_cell(cell: str) -> bool:
        text = (cell or "").strip()
        if not text:
            return False
        if _RE_IS_DATE.search(text):
            return True
        clean = text.replace(",", "").replace("¥", "").replace(" ", "")
        return bool(clean and _RE_IS_AMOUNT.match(clean) and ("." in clean or len(clean) >= 4))

    data_hits = sum(
        1 for row in body if any(_strong_data_cell(str(c or "")) for c in row)
    )
    data_ratio = data_hits / len(body)
    if data_ratio >= 0.25:
        return False
    if len(body) >= 20 and header_score == 0:
        return True
    return len(body) >= 8 and data_ratio < 0.10


def _quarantine_fragment_log(page_no: int, row_count: int) -> dict:
    return {
        "action": "quarantine_fragment",
        "page": page_no,
        "rows": row_count,
    }


def _quarantine_col_mismatch_log(
    page_no: int,
    row_count: int,
    prev_cols: int,
    curr_cols: int,
) -> dict:
    return {
        "action": "quarantine_col_mismatch",
        "page": page_no,
        "rows": row_count,
        "prev_cols": prev_cols,
        "curr_cols": curr_cols,
    }


def collect_cross_page_merge_groups(
    pages: list[PageLayout],
    profile: Any | None = None,
) -> list[dict]:
    """Plan cross-page table merges without mutating pages.

    Returns a list of merge groups, each:
        {"rows": list[list], "pages": list[int], "block": Block, "merge_log": list[dict]}
    """
    if not pages:
        return []

    all_blocks = []
    for page in pages:
        for block in page.blocks:
            all_blocks.append({"block": block, "page_number": page.page_number})

    merged_table_data: list[dict] = []

    for entry in all_blocks:
        block = entry["block"]
        if block.block_type != "table" or not isinstance(block.raw_content, list):
            continue

        curr_rows = block.raw_content
        page_no = entry["page_number"]

        if not merged_table_data:
            start_log: dict = {"action": "start", "page": page_no, "rows": len(curr_rows)}
            if _profile_quarantines_fragments(profile) and _looks_like_fragment_table(curr_rows):
                start_log = _quarantine_fragment_log(page_no, len(curr_rows))
                logger.warning(
                    "[TableMerger] quarantine fragment page %s (%d rows, weak header/data signal)",
                    page_no,
                    len(curr_rows),
                )
            merged_table_data.append(
                {
                    "rows": list(curr_rows),
                    "row_pages": [page_no] * len(curr_rows),
                    "pages": [page_no],
                    "block": block,
                    "merge_log": [start_log],
                }
            )
            continue

        prev = merged_table_data[-1]
        prev_rows = prev["rows"]
        first_row = curr_rows[0] if curr_rows else []
        is_header = _is_header_row(first_row)

        prev_col_count = _median_col_count(prev_rows)
        curr_col_count = _median_col_count(curr_rows)
        col_count_mismatch = abs(prev_col_count - curr_col_count) > 1

        if col_count_mismatch:
            max_cc = max(prev_col_count, curr_col_count, 1)
            min_cc = min(prev_col_count, curr_col_count)
            ratio = min_cc / max_cc
            if ratio < 0.5:
                logger.warning(
                    "[TableMerger] quarantine col-mismatch page "
                    "%s (%s cols vs expected %s) — standalone table preserved",
                    page_no,
                    curr_col_count,
                    prev_col_count,
                )
                merged_table_data.append(
                    {
                        "rows": list(curr_rows),
                        "row_pages": [page_no] * len(curr_rows),
                        "pages": [page_no],
                        "block": block,
                        "merge_log": [
                            {
                                "action": "quarantine_col_mismatch",
                                "page": page_no,
                                "rows": len(curr_rows),
                                "prev_cols": prev_col_count,
                                "curr_cols": curr_col_count,
                            }
                        ],
                    }
                )
                continue
            start_log = {"action": "start", "page": page_no, "rows": len(curr_rows)}
            if _profile_quarantines_fragments(profile) and _looks_like_fragment_table(curr_rows):
                start_log = _quarantine_fragment_log(page_no, len(curr_rows))
                logger.warning(
                    "[TableMerger] quarantine fragment page %s (%d rows, col ratio %.2f)",
                    page_no,
                    len(curr_rows),
                    ratio,
                )
            merged_table_data.append(
                {
                    "rows": list(curr_rows),
                    "row_pages": [page_no] * len(curr_rows),
                    "pages": [page_no],
                    "block": block,
                    "merge_log": [start_log],
                }
            )
        elif is_header and prev_rows:
            prev_header = prev_rows[0] if prev_rows else []
            if headers_match(prev_header, first_row):
                added = curr_rows[1:]
                prev["rows"].extend(added)
                prev.setdefault("row_pages", [prev["pages"][0]] * len(prev_rows))
                prev["row_pages"].extend([page_no] * len(added))
                prev["pages"].append(page_no)
                prev["merge_log"].append(
                    {"action": "merge_header_page", "page": page_no, "rows_added": max(len(curr_rows) - 1, 0)}
                )
            else:
                log_entry: dict = {"action": "start", "page": page_no, "rows": len(curr_rows)}
                if _profile_quarantines_standalone(profile):
                    log_entry = _quarantine_col_mismatch_log(
                        page_no, len(curr_rows), prev_col_count, curr_col_count
                    )
                    logger.warning(
                        "[TableMerger] quarantine header-mismatch page "
                        "%s (%s cols vs expected %s) — standalone table preserved",
                        page_no,
                        curr_col_count,
                        prev_col_count,
                    )
                merged_table_data.append(
                    {
                        "rows": list(curr_rows),
                        "row_pages": [page_no] * len(curr_rows),
                        "pages": [page_no],
                        "block": block,
                        "merge_log": [log_entry],
                    }
                )
        elif not is_header and prev_rows:
            confirmed_hdr = prev_rows[0] if prev_rows else []
            stripped = _strip_preamble(list(curr_rows), confirmed_hdr)
            stripped = [r for r in stripped if any((c or "").strip() for c in r)]
            if stripped:
                prev.setdefault("row_pages", [prev["pages"][0]] * len(prev_rows))
                prev["rows"].extend(stripped)
                prev["row_pages"].extend([page_no] * len(stripped))
                prev["pages"].append(page_no)
                prev["merge_log"].append(
                    {"action": "merge_continuation", "page": page_no, "rows_added": len(stripped)}
                )
        else:
            start_log = {"action": "start", "page": page_no, "rows": len(curr_rows)}
            if _profile_quarantines_fragments(profile) and _looks_like_fragment_table(curr_rows):
                start_log = _quarantine_fragment_log(page_no, len(curr_rows))
                logger.warning(
                    "[TableMerger] quarantine fragment page %s (%d rows)",
                    page_no,
                    len(curr_rows),
                )
            merged_table_data.append(
                {
                    "rows": list(curr_rows),
                    "row_pages": [page_no] * len(curr_rows),
                    "pages": [page_no],
                    "block": block,
                    "merge_log": [start_log],
                }
            )

    for mdata in merged_table_data:
        if len(mdata["pages"]) > 1:
            logger.info(
                "[TableMerger] F-7 audit: merged %d pages → %d rows (table starts page %s)",
                len(mdata["pages"]),
                len(mdata["rows"]),
                mdata["pages"][0],
            )

    return merged_table_data


def merge_cross_page_tables(pages: list[PageLayout]) -> list[PageLayout]:
    """Cross-page table merging — operates at the Block level.

    .. deprecated::
        Prefer ``TableComposer.from_page_layouts()`` + dual-view mode.
        This destructive merge mutates physical pages and will be removed.

    Args:
        pages: List of PageLayout objects for all pages.

    Returns:
        PageLayout list with cross-page tables merged.
    """
    import warnings

    warnings.warn(
        "merge_cross_page_tables() is deprecated; use TableComposer dual-view instead",
        DeprecationWarning,
        stacklevel=2,
    )
    if len(pages) <= 1:
        return pages

    all_blocks = []
    for page in pages:
        for block in page.blocks:
            all_blocks.append(
                {
                    "block": block,
                    "page_number": page.page_number,
                }
            )

    merged_table_data = collect_cross_page_merge_groups(pages, profile=None)
    non_table_blocks: list[dict] = [
        entry
        for entry in all_blocks
        if entry["block"].block_type != "table"
        or not isinstance(entry["block"].raw_content, list)
    ]

    new_pages = []
    for page in pages:
        page_blocks: list[Block] = []
        for entry in non_table_blocks:
            if entry["page_number"] == page.page_number:
                page_blocks.append(entry["block"])

        for mdata in merged_table_data:
            if mdata["pages"][0] == page.page_number:
                original = mdata["block"]
                merged_block = Block(
                    block_id=original.block_id,
                    block_type="table",
                    bbox=original.bbox,
                    reading_order=original.reading_order,
                    page=original.page,
                    raw_content=mdata["rows"],
                )
                page_blocks.append(merged_block)

        page_blocks.sort(key=lambda b: b.reading_order)

        new_page = PageLayout(
            page_number=page.page_number,
            width=page.width,
            height=page.height,
            blocks=tuple(page_blocks),
            semantic_zones=page.semantic_zones,
            is_scanned=page.is_scanned,
        )
        new_pages.append(new_page)

    return new_pages


def collect_quarantined_tables(
    pages: list[PageLayout],
    profile: Any | None = None,
) -> list[dict]:
    """Collect quarantine records from cross-page merge planning (P3-2).

    Each entry describes a physical table kept standalone because column counts
    were incompatible with the preceding merge group (ratio < 0.5), or because a
    borderless ledger profile quarantined a header-mismatch tail page.
    """
    groups = collect_cross_page_merge_groups(pages, profile=profile)
    quarantined: list[dict] = []
    for group in groups:
        for entry in group.get("merge_log") or []:
            action = entry.get("action")
            reason = _QUARANTINE_ACTIONS.get(action or "")
            if not reason:
                continue
            item = {
                "page": entry.get("page"),
                "row_count": entry.get("rows"),
                "reason": reason,
                "action": "standalone_physical_table",
            }
            if action == "quarantine_col_mismatch":
                item["prev_cols"] = entry.get("prev_cols")
                item["curr_cols"] = entry.get("curr_cols")
            quarantined.append(item)
    return quarantined
