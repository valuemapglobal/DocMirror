"""Cross-page fusion for the UDTR structure layer."""

from __future__ import annotations

import logging
from typing import Any

from docmirror.layout.vocabulary import KNOWN_HEADER_WORDS
from docmirror.models.entities.domain import Block, PageLayout

logger = logging.getLogger(__name__)

_QUARANTINE_MERGE_ACTIONS = frozenset({"quarantine_col_mismatch", "quarantine_fragment"})
_QUARANTINE_ACTIONS = {
    "quarantine_col_mismatch": "col_count_mismatch",
    "quarantine_fragment": "fragment_table",
}


class CrossPageFusion:
    """Unified cross-page fusion for tables, prose, and sections."""

    def fuse(self, blocks: list[Any], pages: list[Any], evidence_plane: Any = None) -> dict[str, Any]:
        table_groups = collect_cross_page_merge_groups(pages) if pages else []
        prose_edges = _cross_page_prose_edges(blocks)
        sections = _section_ranges(blocks, len(pages))
        return {
            "table_fusions": table_groups,
            "prose_fusions": prose_edges,
            "sections": sections,
            "quality": {
                "tables": len([g for g in table_groups if len(g.get("pages", [])) > 1]),
                "prose": len(prose_edges),
                "sections": len(sections),
            },
        }


def is_quarantined_merge_group(group: dict[str, Any]) -> bool:
    """Return True when merge planning marked this group as physical quarantine."""
    for entry in group.get("merge_log") or []:
        if entry.get("action") in _QUARANTINE_MERGE_ACTIONS:
            return True
    return False


def collect_cross_page_merge_groups(
    pages: list[PageLayout],
    profile: Any | None = None,
) -> list[dict[str, Any]]:
    """Plan cross-page table merges without mutating physical pages."""
    if not pages:
        return []

    merged_table_data: list[dict[str, Any]] = []
    for page in pages:
        for block in getattr(page, "blocks", ()) or ():
            if _block_type(block) != "table" or not isinstance(_block_rows(block), list):
                continue

            curr_rows = _block_rows(block)
            page_no = int(getattr(page, "page_number", 0) or _block_page(block) or 0)
            if not merged_table_data:
                merged_table_data.append(_new_group(block, curr_rows, page_no, profile))
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
                        "[TableMerger] quarantine col-mismatch page %s (%s cols vs expected %s)",
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
                                _quarantine_col_mismatch_log(
                                    page_no,
                                    len(curr_rows),
                                    prev_col_count,
                                    curr_col_count,
                                )
                            ],
                        }
                    )
                    continue
                merged_table_data.append(_new_group(block, curr_rows, page_no, profile))
            elif is_header and prev_rows:
                prev_header = prev_rows[0] if prev_rows else []
                if _headers_match(prev_header, first_row):
                    added = curr_rows[1:]
                    prev.setdefault("row_pages", [prev["pages"][0]] * len(prev_rows))
                    prev["rows"].extend(added)
                    prev["row_pages"].extend([page_no] * len(added))
                    prev["pages"].append(page_no)
                    prev["merge_log"].append(
                        {"action": "merge_header_page", "page": page_no, "rows_added": max(len(curr_rows) - 1, 0)}
                    )
                else:
                    log_entry: dict[str, Any] = {"action": "start", "page": page_no, "rows": len(curr_rows)}
                    if _profile_quarantines_standalone(profile):
                        log_entry = _quarantine_col_mismatch_log(
                            page_no, len(curr_rows), prev_col_count, curr_col_count
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
                if _profile_quarantines_standalone(profile) and len(curr_rows) <= 2:
                    merged_table_data.append(
                        {
                            "rows": list(curr_rows),
                            "row_pages": [page_no] * len(curr_rows),
                            "pages": [page_no],
                            "block": block,
                            "merge_log": [
                                _quarantine_col_mismatch_log(
                                    page_no,
                                    len(curr_rows),
                                    prev_col_count,
                                    curr_col_count,
                                )
                            ],
                        }
                    )
                    continue
                confirmed_hdr = prev_rows[0] if prev_rows else []
                stripped = _strip_preamble(list(curr_rows), confirmed_hdr)
                stripped = [r for r in stripped if any(str(c or "").strip() for c in r)]
                if stripped:
                    prev.setdefault("row_pages", [prev["pages"][0]] * len(prev_rows))
                    prev["rows"].extend(stripped)
                    prev["row_pages"].extend([page_no] * len(stripped))
                    prev["pages"].append(page_no)
                    prev["merge_log"].append(
                        {"action": "merge_continuation", "page": page_no, "rows_added": len(stripped)}
                    )
            else:
                merged_table_data.append(_new_group(block, curr_rows, page_no, profile))

    for group in merged_table_data:
        if len(group["pages"]) > 1:
            logger.info(
                "[TableMerger] merged %d pages -> %d rows (table starts page %s)",
                len(group["pages"]),
                len(group["rows"]),
                group["pages"][0],
            )
    return merged_table_data


def merge_cross_page_tables(pages: list[PageLayout], evidence_plane: Any = None) -> list[PageLayout]:
    """Return pages with continuation table rows merged into their first page."""
    if len(pages) <= 1:
        return pages

    groups = collect_cross_page_merge_groups(pages)
    new_pages: list[PageLayout] = []
    for page in pages:
        page_blocks: list[Block] = [
            block
            for block in getattr(page, "blocks", ()) or ()
            if _block_type(block) != "table" or not isinstance(_block_rows(block), list)
        ]
        for group in groups:
            if group["pages"][0] != page.page_number:
                continue
            original = group["block"]
            page_blocks.append(
                Block(
                    block_id=getattr(original, "block_id", ""),
                    block_type="table",
                    bbox=getattr(original, "bbox", (0.0, 0.0, 0.0, 0.0)),
                    reading_order=getattr(original, "reading_order", 0),
                    page=getattr(original, "page", page.page_number),
                    raw_content=group["rows"],
                )
            )
        page_blocks.sort(key=lambda b: getattr(b, "reading_order", 0))
        new_pages.append(
            PageLayout(
                page_number=page.page_number,
                width=getattr(page, "width", 0.0),
                height=getattr(page, "height", 0.0),
                blocks=tuple(page_blocks),
                semantic_zones=getattr(page, "semantic_zones", {}),
                is_scanned=getattr(page, "is_scanned", False),
            )
        )
    _verify_cross_page_column_boundaries(new_pages)
    return new_pages


def collect_quarantined_tables(
    pages: list[PageLayout],
    profile: Any | None = None,
) -> list[dict[str, Any]]:
    """Collect quarantine records from cross-page merge planning."""
    groups = collect_cross_page_merge_groups(pages, profile=profile)
    quarantined: list[dict[str, Any]] = []
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


def _new_group(block: Any, rows: list[list[Any]], page_no: int, profile: Any | None) -> dict[str, Any]:
    start_log: dict[str, Any] = {"action": "start", "page": page_no, "rows": len(rows)}
    if _profile_quarantines_fragments(profile) and _looks_like_fragment_table(rows):
        start_log = _quarantine_fragment_log(page_no, len(rows))
        logger.warning("[TableMerger] quarantine fragment page %s (%d rows)", page_no, len(rows))
    return {
        "rows": list(rows),
        "row_pages": [page_no] * len(rows),
        "pages": [page_no],
        "block": block,
        "merge_log": [start_log],
    }


def _block_type(block: Any) -> str:
    return str(getattr(block, "block_type", "") or (block.get("block_type", "") if isinstance(block, dict) else ""))


def _block_rows(block: Any) -> Any:
    return getattr(block, "raw_content", None) if not isinstance(block, dict) else block.get("raw_content")


def _block_page(block: Any) -> int:
    return int(getattr(block, "page", 0) or (block.get("page", 0) if isinstance(block, dict) else 0))


def _median_col_count(rows: list[Any]) -> int:
    counts = sorted(len(row) for row in rows if isinstance(row, (list, tuple)))
    if not counts:
        return 0
    return counts[len(counts) // 2]


def _profile_quarantines_standalone(profile: Any | None) -> bool:
    if profile is None:
        return False
    return bool(
        getattr(profile, "merge_quarantine_on_col_mismatch", False)
        and getattr(profile, "is_borderless_ledger", lambda: False)()
    )


def _profile_quarantines_fragments(profile: Any | None) -> bool:
    if profile is None:
        return False
    return bool(getattr(profile, "merge_quarantine_fragments", False))


def _looks_like_fragment_table(rows: list[Any]) -> bool:
    if not rows or len(rows) < 8:
        return False
    header_cells = [str(c or "") for c in (rows[0] if rows else [])]
    if _header_score(header_cells) >= 2:
        return False
    body = rows[1:] if len(rows) > 1 else list(rows)
    if not body:
        return True
    data_hits = sum(1 for row in body if any(_strong_data_cell(str(c or "")) for c in row))
    data_ratio = data_hits / len(body)
    if data_ratio >= 0.25:
        return False
    if len(body) >= 20 and _header_score(header_cells) == 0:
        return True
    return len(body) >= 8 and data_ratio < 0.10


def _strong_data_cell(text: str) -> bool:
    value = text.strip()
    if not value:
        return False
    if _looks_like_date(value):
        return True
    clean = value.replace(",", "").replace("¥", "").replace(" ", "")
    return _looks_like_amount(clean) and ("." in clean or len(clean) >= 4)


def _is_header_row(row: Any) -> bool:
    if not isinstance(row, (list, tuple)) or not row:
        return False
    cells = [str(cell or "").strip() for cell in row]
    non_empty = [cell for cell in cells if cell]
    if len(non_empty) < 2:
        return False
    return _header_score(non_empty) >= min(2, len(non_empty))


def _header_score(cells: list[str]) -> int:
    score = 0
    for cell in cells:
        lower = cell.lower()
        if any(keyword.lower() in lower for keyword in KNOWN_HEADER_WORDS):
            score += 1
    return score


def _headers_match(left: Any, right: Any) -> bool:
    if not isinstance(left, (list, tuple)) or not isinstance(right, (list, tuple)):
        return False
    left_norm = [_norm_header_cell(cell) for cell in left if _norm_header_cell(cell)]
    right_norm = [_norm_header_cell(cell) for cell in right if _norm_header_cell(cell)]
    if not left_norm or not right_norm:
        return False
    overlap = len(set(left_norm) & set(right_norm))
    return overlap / max(len(set(left_norm)), len(set(right_norm)), 1) >= 0.6


def _norm_header_cell(cell: Any) -> str:
    return "".join(ch for ch in str(cell or "").lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def _strip_preamble(rows: list[list[Any]], confirmed_header: list[Any]) -> list[list[Any]]:
    if not rows:
        return []
    if confirmed_header and rows and _headers_match(confirmed_header, rows[0]):
        return rows[1:]
    return rows


def _looks_like_date(value: str) -> bool:
    digits = [ch for ch in value if ch.isdigit()]
    return len(digits) >= 6 and any(sep in value for sep in ("-", "/", ".", "年", "月"))


def _looks_like_amount(value: str) -> bool:
    if not value:
        return False
    if value.count(".") > 1:
        return False
    if value[0] in "+-":
        value = value[1:]
    return bool(value) and all(ch.isdigit() or ch == "." for ch in value)


def _quarantine_fragment_log(page_no: int, row_count: int) -> dict[str, Any]:
    return {"action": "quarantine_fragment", "page": page_no, "rows": row_count}


def _quarantine_col_mismatch_log(
    page_no: int,
    row_count: int,
    prev_cols: int,
    curr_cols: int,
) -> dict[str, Any]:
    return {
        "action": "quarantine_col_mismatch",
        "page": page_no,
        "rows": row_count,
        "prev_cols": prev_cols,
        "curr_cols": curr_cols,
    }


def _verify_cross_page_column_boundaries(pages: list[PageLayout]) -> dict[str, Any]:
    col_counts: list[tuple[int, int]] = []
    for page in pages:
        for block in getattr(page, "blocks", ()) or ():
            if _block_type(block) != "table":
                continue
            rows = _block_rows(block)
            if not isinstance(rows, list) or not rows or not isinstance(rows[0], (list, tuple)):
                continue
            col_counts.append((int(getattr(page, "page_number", 0)), len(rows[0])))
            break
    if not col_counts:
        return {"pages_checked": 0, "stable": True}
    counts = [count for _, count in col_counts]
    stable = min(counts) == max(counts)
    result: dict[str, Any] = {
        "pages_checked": len(col_counts),
        "col_counts": col_counts,
        "stable": stable,
        "min_count": min(counts),
        "max_count": max(counts),
    }
    if not stable:
        result["deviation"] = max(counts) - min(counts)
    return result


def _cross_page_prose_edges(blocks: list[Any]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    previous = None
    for block in blocks:
        block_type = getattr(block, "type", None) or getattr(block, "block_type", None)
        if str(block_type) not in {"paragraph", "text"}:
            previous = block
            continue
        page = getattr(block, "page_number", None) or getattr(block, "page", None)
        prev_page = getattr(previous, "page_number", None) or getattr(previous, "page", None) if previous else None
        if previous is not None and page is not None and prev_page is not None and page == prev_page + 1:
            edges.append(
                {"from": getattr(previous, "id", ""), "to": getattr(block, "id", ""), "type": "cross_page_prose"}
            )
        previous = block
    return edges


def _section_ranges(blocks: list[Any], page_count: int) -> list[dict[str, Any]]:
    headings = [
        b for b in blocks if str(getattr(b, "type", "") or getattr(b, "block_type", "")) in {"heading", "title"}
    ]
    sections: list[dict[str, Any]] = []
    for index, heading in enumerate(headings):
        start_page = int(getattr(heading, "page_number", None) or getattr(heading, "page", 1) or 1)
        end_page = page_count
        if index + 1 < len(headings):
            next_page = int(
                getattr(headings[index + 1], "page_number", None)
                or getattr(headings[index + 1], "page", start_page)
                or start_page
            )
            end_page = max(start_page, next_page - 1)
        sections.append(
            {
                "heading": getattr(heading, "id", None) or getattr(heading, "block_id", ""),
                "start_page": start_page,
                "end_page": end_page,
            }
        )
    return sections


__all__ = [
    "CrossPageFusion",
    "collect_cross_page_merge_groups",
    "collect_quarantined_tables",
    "is_quarantined_merge_group",
    "merge_cross_page_tables",
]
