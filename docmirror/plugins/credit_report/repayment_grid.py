# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Credit-report repayment micro-grid reconstruction."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from docmirror.core.ocr.micro_grid.cell_recognition import (
    normalize_allowlist_text,
    recognize_micro_cell_from_image,
)
from docmirror.core.ocr.micro_grid.detect import detect_micro_grid_candidates
from docmirror.core.ocr.micro_grid.models import BBox, MicroGrid, MicroGridCell, OCRToken
from docmirror.core.ocr.micro_grid.reconstruct import (
    assign_tokens_to_col_bands,
    build_cell,
    cell_bbox,
    dedupe_visual_tokens,
    equal_col_bands,
    expand_tokens_to_char_tokens,
)

_RANGE_RE = re.compile(r"(20\d{2})年\s*(\d{1,2})月\s*[-—一至~～]\s*(20\d{2})年\s*(\d{1,2})月.*还款记录")
_YEAR_RE = re.compile(r"^20\d{2}$")
_STATUS_CHARS = {"N", "C", "1", "2", "3", "4", "5", "6", "7"}


@dataclass(frozen=True)
class RepaymentExtraction:
    micro_grid: MicroGrid | None
    records: list[dict[str, Any]]
    audit: dict[str, Any]


def _bbox(obj: Any) -> BBox | None:
    raw = obj.get("bbox") if isinstance(obj, dict) else getattr(obj, "bbox", None)
    if raw and len(raw) == 4:
        return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    return None


def _text(obj: Any) -> str:
    if isinstance(obj, dict):
        return str(obj.get("content") or obj.get("text") or "").strip()
    return str(getattr(obj, "text", "") or "").strip()


def _confidence(obj: Any) -> float:
    val = obj.get("confidence") if isinstance(obj, dict) else getattr(obj, "confidence", 1.0)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 1.0


def _line_items(lines: Iterable[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, line in enumerate(lines):
        b = _bbox(line)
        t = _text(line)
        if not b or not t:
            continue
        out.append({"idx": idx, "text": t, "bbox": b, "confidence": _confidence(line)})
    out.sort(key=lambda x: (x["bbox"][1], x["bbox"][0]))
    return out


def _months_between(start_year: int, start_month: int, end_year: int, end_month: int) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        months.append((y, m))
        m += 1
        if m > 12:
            y += 1
            m = 1
    return months


def _expand_line_to_char_tokens(line: dict[str, Any], *, page: int, prefix: str) -> list[OCRToken]:
    """Split a merged OCR line into approximate single-character tokens."""
    text = line["text"]
    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return []
    x0, y0, x1, y1 = line["bbox"]
    width = max(x1 - x0, 1.0)
    step = width / len(chars)
    tokens = []
    for i, ch in enumerate(chars):
        tokens.append(
            OCRToken(
                token_id=f"{prefix}_{line['idx']}_{i}",
                text=ch,
                bbox=(x0 + step * i, y0, x0 + step * (i + 1), y1),
                confidence=line.get("confidence", 1.0),
                page=page,
                source="ocr_line_split",
                source_token_id=f"line_{line['idx']}",
            )
        )
    return tokens


def _cell_bbox(row_band: dict[str, Any], col_band: dict[str, Any]) -> BBox:
    return cell_bbox(row_band, col_band)


def _assign_row(
    tokens: list[OCRToken], row_band: dict[str, Any], cols: list[dict[str, Any]]
) -> dict[int, list[OCRToken]]:
    return assign_tokens_to_col_bands(tokens, row_band, cols)


def _token_text(tokens: list[OCRToken], *, allowed: set[str] | None = None) -> str:
    ordered = sorted(tokens, key=lambda t: (t.bbox[0], t.bbox[1]))
    text = "".join(t.text for t in ordered).strip()
    if allowed is not None:
        text = "".join(ch for ch in text if ch in allowed)
    return text


def _line_split_tokens_under_anchor(line_items: list[dict[str, Any]], *, ay1: float, page: int) -> list[OCRToken]:
    out: list[OCRToken] = []
    for line in line_items:
        ly0 = line["bbox"][1]
        if ay1 <= ly0 <= ay1 + 170:
            out.extend(_expand_line_to_char_tokens(line, page=page, prefix=f"ocr_p{page}_repay"))
    return out


def _normalize_amount_text(text: str) -> str:
    normalized = normalize_allowlist_text(text, set("0123456789.,"), max_chars=16)
    compact = normalized.replace(",", "").replace(".", "")
    if compact and set(compact) == {"0"}:
        return "0"
    return normalized


def _find_anchor(lines: list[dict[str, Any]]) -> tuple[dict[str, Any], tuple[int, int, int, int]] | None:
    for line in lines:
        normalized = line["text"].replace(" ", "")
        m = _RANGE_RE.search(normalized)
        if m:
            sy, sm, ey, em = map(int, m.groups())
            return line, (sy, sm, ey, em)
    return None


def _nearest_year_lines(lines: list[dict[str, Any]], anchor: dict[str, Any]) -> list[dict[str, Any]]:
    ax0, ay0, ax1, ay1 = anchor["bbox"]
    candidates = [
        line
        for line in lines
        if _YEAR_RE.match(line["text"].strip()) and line["bbox"][1] > ay1 and line["bbox"][1] < ay1 + 160
    ]
    return candidates[:4]


def _month_col_bands(header_line: dict[str, Any], *, n_months: int = 12) -> list[dict[str, Any]]:
    return equal_col_bands(header_line["bbox"], count=n_months, start_index=1, role="month")


def _coerce_token(obj: Any, *, page: int, idx: int) -> OCRToken | None:
    if isinstance(obj, OCRToken):
        return obj
    b = _bbox(obj)
    text = _text(obj)
    if not b or not text:
        return None
    token_id = obj.get("token_id") if isinstance(obj, dict) else getattr(obj, "token_id", None)
    raw_bbox = obj.get("raw_bbox") if isinstance(obj, dict) else getattr(obj, "raw_bbox", None)
    raw: BBox | None = None
    if raw_bbox and len(raw_bbox) == 4:
        raw = (float(raw_bbox[0]), float(raw_bbox[1]), float(raw_bbox[2]), float(raw_bbox[3]))
    return OCRToken(
        token_id=str(token_id or f"ocr_p{page}_t{idx}"),
        text=text,
        bbox=b,
        confidence=_confidence(obj),
        page=page,
        source=str(obj.get("source", "rapidocr") if isinstance(obj, dict) else getattr(obj, "source", "rapidocr")),
        coordinate_system=str(
            obj.get("coordinate_system", "pdf_points_top_left")
            if isinstance(obj, dict)
            else getattr(obj, "coordinate_system", "pdf_points_top_left")
        ),
        raw_bbox=raw,
        raw_coordinate_system=str(
            obj.get("raw_coordinate_system", "image_pixels")
            if isinstance(obj, dict)
            else getattr(obj, "raw_coordinate_system", "image_pixels")
        ),
    )


def _coerce_tokens(tokens: Iterable[Any] | None, *, page: int) -> list[OCRToken]:
    out: list[OCRToken] = []
    for idx, token in enumerate(tokens or []):
        coerced = _coerce_token(token, page=page, idx=idx)
        if coerced is not None:
            out.append(coerced)
    return out


def _row_band(line: dict[str, Any], role: str, *, x0: float, x1: float, pad_y: float = 3.0) -> dict[str, Any]:
    _lx0, y0, _lx1, y1 = line["bbox"]
    return {
        "index": -1,
        "role": role,
        "bbox": [x0, y0 - pad_y, x1, y1 + pad_y],
        "geometry_status": "estimated",
        "source_line_index": line["idx"],
    }


def _line_after(
    lines: list[dict[str, Any]], y: float, *, x_min: float, x_max: float, max_gap: float = 55.0
) -> dict[str, Any] | None:
    candidates = []
    for line in lines:
        lx0, ly0, lx1, ly1 = line["bbox"]
        if ly0 <= y or ly0 - y > max_gap:
            continue
        if lx1 < x_min or lx0 > x_max:
            continue
        candidates.append(line)
    return candidates[0] if candidates else None


def _line_before(
    lines: list[dict[str, Any]], y: float, *, x_min: float, x_max: float, max_gap: float = 55.0
) -> dict[str, Any] | None:
    candidates = []
    for line in lines:
        lx0, ly0, lx1, ly1 = line["bbox"]
        if ly0 >= y or y - ly0 > max_gap:
            continue
        if lx1 < x_min or lx0 > x_max:
            continue
        candidates.append(line)
    return candidates[-1] if candidates else None


def reconstruct_repayment_micro_grid_from_lines(
    lines: Iterable[Any],
    *,
    page: int,
    tokens: Iterable[Any] | None = None,
    page_width: float | None = None,
    page_height: float | None = None,
    page_image: Any | None = None,
    enable_cell_ocr: bool = False,
) -> RepaymentExtraction:
    """Reconstruct a credit repayment grid from OCR line-level geometry."""
    line_items = _line_items(lines)
    evidence_tokens = _coerce_tokens(tokens, page=page)
    candidates = detect_micro_grid_candidates(
        evidence_tokens,
        lines=line_items,
        page=page,
        page_width=page_width,
        page_height=page_height,
    )
    found = _find_anchor(line_items)
    if not found:
        return RepaymentExtraction(
            None,
            [],
            {
                "reason": "anchor_not_found",
                "micro_grid_candidates": [candidate.to_dict() for candidate in candidates],
            },
        )

    anchor, (start_year, start_month, end_year, end_month) = found
    ax0, ay0, ax1, ay1 = anchor["bbox"]
    header_line = _line_after(line_items, ay1, x_min=ax0 - 220, x_max=ax1 + 260, max_gap=35.0)
    if header_line is None:
        return RepaymentExtraction(None, [], {"reason": "month_header_not_found", "anchor": anchor})

    years = _nearest_year_lines(line_items, anchor)
    if not years:
        return RepaymentExtraction(None, [], {"reason": "year_rows_not_found", "anchor": anchor})

    month_cols = _month_col_bands(header_line)
    month_x0 = min(col["bbox"][0] for col in month_cols)
    grid_x1 = max(col["bbox"][2] for col in month_cols)
    year_x0 = min(float(year_line["bbox"][0]) for year_line in years)
    year_x1 = max(float(year_line["bbox"][2]) for year_line in years)
    year_y1 = max(float(year_line["bbox"][3]) for year_line in years)
    year_col_band = {
        "index": 0,
        "header": "year",
        "role": "year",
        "bbox": [year_x0, header_line["bbox"][1], max(month_x0, year_x1), year_y1],
        "geometry_status": "estimated",
    }
    grid_x0 = min(float(year_col_band["bbox"][0]), month_x0)

    synthetic_tokens: list[OCRToken] = []
    if evidence_tokens:
        roi_tokens = [token for token in evidence_tokens if ay1 <= token.center[1] <= ay1 + 170]
        synthetic_tokens = expand_tokens_to_char_tokens(roi_tokens)
        synthetic_tokens.extend(_line_split_tokens_under_anchor(line_items, ay1=ay1, page=page))
        synthetic_tokens = dedupe_visual_tokens(synthetic_tokens)
        token_source = "ocr_tokens+line_bbox_fallback+char_split"
    else:
        synthetic_tokens.extend(_line_split_tokens_under_anchor(line_items, ay1=ay1, page=page))
        synthetic_tokens = dedupe_visual_tokens(synthetic_tokens)
        token_source = "ocr_line_bbox+char_split"

    row_bands: list[dict[str, Any]] = []
    cell_rows: list[list[MicroGridCell]] = []

    anchor_band = _row_band(anchor, "anchor", x0=grid_x0, x1=grid_x1)
    anchor_band["index"] = 0
    row_bands.append(anchor_band)
    anchor_col = {
        "index": 0,
        "header": "anchor",
        "role": "anchor",
        "bbox": list(anchor["bbox"]),
        "geometry_status": "exact",
    }
    cell_rows.append(
        [
            build_cell(
                row_band=anchor_band,
                col_band=anchor_col,
                tokens=[],
                text=anchor["text"],
                role="anchor",
            )
        ]
    )

    header_band = _row_band(header_line, "month_header", x0=grid_x0, x1=grid_x1)
    header_band["index"] = 1
    row_bands.append(header_band)
    header_col = {
        "index": 0,
        "header": "months",
        "role": "month_header",
        "bbox": list(header_line["bbox"]),
        "geometry_status": "exact",
    }
    cell_rows.append(
        [
            build_cell(
                row_band=header_band,
                col_band=header_col,
                tokens=[],
                text=header_line["text"],
                role="month_header",
            )
        ]
    )

    records: list[dict[str, Any]] = []
    record_months = set(_months_between(start_year, start_month, end_year, end_month))
    crop_ocr_attempts = 0
    crop_ocr_hits = 0

    for year_line in years:
        year = int(year_line["text"])
        status_line = _line_before(
            line_items, year_line["bbox"][1], x_min=grid_x0 - 10, x_max=grid_x1 + 10, max_gap=55.0
        )
        if status_line is None or status_line is header_line or "还款记录" in status_line["text"]:
            status_line = _line_after(
                line_items, year_line["bbox"][1], x_min=grid_x0 - 10, x_max=grid_x1 + 10, max_gap=55.0
            )
        if status_line is None:
            continue
        amount_line = _line_after(
            line_items, status_line["bbox"][1], x_min=grid_x0 - 10, x_max=grid_x1 + 10, max_gap=35.0
        )
        if amount_line and _YEAR_RE.match(amount_line["text"].strip()):
            amount_line = _line_after(
                line_items, amount_line["bbox"][1], x_min=grid_x0 - 10, x_max=grid_x1 + 10, max_gap=35.0
            )

        status_band = _row_band(status_line, "status", x0=grid_x0, x1=grid_x1)
        status_band["index"] = len(row_bands)
        row_bands.append(status_band)
        amount_band = None
        if amount_line is not None:
            amount_band = _row_band(amount_line, "overdue_amount", x0=grid_x0, x1=grid_x1)
            amount_band["index"] = len(row_bands)
            row_bands.append(amount_band)

        year_col = {
            "index": 0,
            "header": str(year),
            "role": "year",
            "bbox": list(year_line["bbox"]),
            "geometry_status": "exact",
        }
        status_cells: list[MicroGridCell] = [
            build_cell(
                row_band=status_band,
                col_band=year_col,
                tokens=[],
                text=str(year),
                role="year",
            )
        ]
        amount_cells: list[MicroGridCell] = []
        raw_status_text = status_line["text"].replace(" ", "")
        status_chars = [ch for ch in raw_status_text if ch in _STATUS_CHARS]
        # Domain correction: closed credit-report rows commonly render the final
        # month as C. If OCR collapsed a two-month N/C row into "CN", use the
        # anchor date range and visual convention to place C on the final month.
        if year == end_year and len(status_chars) == 2 and set(status_chars) == {"N", "C"}:
            active_months = [month for yy, month in sorted(record_months) if yy == year]
            if len(active_months) == 2:
                status_by_month = {active_months[0]: "N", active_months[1]: "C"}
            else:
                status_by_month = {}
        else:
            status_by_month = {}

        status_assignments = _assign_row(synthetic_tokens, status_band, month_cols)
        amount_assignments = _assign_row(synthetic_tokens, amount_band, month_cols) if amount_band is not None else {}

        for col in month_cols:
            month = int(col["header"])
            st_tokens = status_assignments.get(month, [])
            status = normalize_allowlist_text(
                status_by_month.get(month) or _token_text(st_tokens), _STATUS_CHARS, max_chars=1
            )
            status_crop = None
            status_recognition_source = "tokens"
            status_recognition_audit: dict[str, Any] = {}
            if (
                not status
                and enable_cell_ocr
                and page_image is not None
                and page_width is not None
                and page_height is not None
                and (year, month) in record_months
            ):
                crop_ocr_attempts += 1
                rec = recognize_micro_cell_from_image(
                    page_image,
                    _cell_bbox(status_band, col),
                    page_width=page_width,
                    page_height=page_height,
                    allowed_charset=_STATUS_CHARS,
                    max_chars=1,
                )
                status_crop = rec.raw_text
                status_recognition_source = rec.source
                status_recognition_audit = rec.audit
                if rec.text:
                    crop_ocr_hits += 1
                    status = rec.text
            if len(status) > 1:
                status = status[0]
            st_cell = build_cell(
                row_band=status_band,
                col_band=col,
                tokens=st_tokens,
                text=status,
                role="status",
                crop_ocr_text=status_crop,
                recognition_source=status_recognition_source,
                recognition_audit=status_recognition_audit,
            )
            status_cells.append(st_cell)

            amount = ""
            amount_bbox = None
            if amount_band is not None:
                amt_tokens = amount_assignments.get(month, [])
                amount = _normalize_amount_text(_token_text(amt_tokens))
                amount_bbox = _cell_bbox(amount_band, col)
                amount_crop = None
                amount_recognition_source = "tokens"
                amount_recognition_audit: dict[str, Any] = {}
                if (
                    not amount
                    and enable_cell_ocr
                    and page_image is not None
                    and page_width is not None
                    and page_height is not None
                    and (year, month) in record_months
                ):
                    crop_ocr_attempts += 1
                    rec = recognize_micro_cell_from_image(
                        page_image,
                        amount_bbox,
                        page_width=page_width,
                        page_height=page_height,
                        allowed_charset=set("0123456789.,"),
                        max_chars=16,
                    )
                    amount_crop = rec.raw_text
                    amount_recognition_source = rec.source
                    amount_recognition_audit = rec.audit
                    if rec.text:
                        crop_ocr_hits += 1
                        amount = _normalize_amount_text(rec.text)
                amount_cells.append(
                    build_cell(
                        row_band=amount_band,
                        col_band=col,
                        tokens=amt_tokens,
                        text=amount,
                        role="overdue_amount",
                        crop_ocr_text=amount_crop,
                        recognition_source=amount_recognition_source,
                        recognition_audit=amount_recognition_audit,
                    )
                )

            if (year, month) in record_months and status:
                status_ref = {
                    "page": page,
                    "grid_id": f"mg_p{page}_repayment_0",
                    "row": st_cell.row_index,
                    "col": month,
                }
                refs = [status_ref]
                if amount_band is not None:
                    refs.append(
                        {"page": page, "grid_id": f"mg_p{page}_repayment_0", "row": amount_band["index"], "col": month}
                    )
                records.append(
                    {
                        "year": year,
                        "month": month,
                        "status": status,
                        "overdue_amount": amount or "0",
                        "status_bbox": list(st_cell.bbox),
                        **({"amount_bbox": list(amount_bbox)} if amount_bbox else {}),
                        "source_cell_refs": refs,
                        "confidence": st_cell.confidence or 0.7,
                    }
                )
        cell_rows.append(status_cells)
        if amount_cells:
            cell_rows.append(amount_cells)

    if not records:
        return RepaymentExtraction(None, [], {"reason": "no_records_projected", "anchor": anchor})

    all_y = [anchor["bbox"][1], header_line["bbox"][1]]
    all_y.extend(b["bbox"][1] for b in row_bands)
    all_y.extend(b["bbox"][3] for b in row_bands)
    all_y.extend(float(year_line["bbox"][1]) for year_line in years)
    all_y.extend(float(year_line["bbox"][3]) for year_line in years)
    grid_bbox = (grid_x0, min(all_y), grid_x1, max(all_y))
    micro_grid = MicroGrid(
        grid_id=f"mg_p{page}_repayment_0",
        page=page,
        bbox=grid_bbox,
        anchor_text=anchor["text"],
        row_bands=row_bands,
        col_bands=[year_col_band, *month_cols],
        cells=cell_rows,
        grid_type_hint="credit_repayment_record",
        geometry_source=f"{token_source}+estimated_month_bands",
        confidence=0.82,
        audit={
            "anchor_line_index": anchor["idx"],
            "header_line_index": header_line["idx"],
            "micro_grid_candidates": [candidate.to_dict() for candidate in candidates],
            "date_range": {
                "start_year": start_year,
                "start_month": start_month,
                "end_year": end_year,
                "end_month": end_month,
            },
            "token_count": len(synthetic_tokens),
            "source_token_count": len(evidence_tokens),
            "cell_crop_ocr": {
                "enabled": bool(enable_cell_ocr),
                "attempts": crop_ocr_attempts,
                "hits": crop_ocr_hits,
            },
        },
    )
    return RepaymentExtraction(micro_grid, records, {"reason": "ok", "record_count": len(records)})


def extract_credit_repayment_records(
    lines: Iterable[Any],
    *,
    page: int,
    tokens: Iterable[Any] | None = None,
    page_width: float | None = None,
    page_height: float | None = None,
    page_image: Any | None = None,
    enable_cell_ocr: bool = False,
) -> dict[str, Any]:
    extraction = reconstruct_repayment_micro_grid_from_lines(
        lines,
        page=page,
        tokens=tokens,
        page_width=page_width,
        page_height=page_height,
        page_image=page_image,
        enable_cell_ocr=enable_cell_ocr,
    )
    return {
        "micro_grid": extraction.micro_grid.to_dict() if extraction.micro_grid else None,
        "repayment_records": extraction.records,
        "audit": extraction.audit,
    }


def _date_range_from_grid(grid: dict[str, Any]) -> tuple[int, int, int, int] | None:
    audit_range = (grid.get("audit") or {}).get("date_range") or {}
    if audit_range.get("start_year") and audit_range.get("end_year"):
        return (
            int(audit_range["start_year"]),
            int(audit_range.get("start_month") or 1),
            int(audit_range["end_year"]),
            int(audit_range.get("end_month") or 12),
        )
    match = _RANGE_RE.search(str(grid.get("anchor_text") or ""))
    if not match:
        return None
    return tuple(int(v) for v in match.groups())  # type: ignore[return-value]


def _years_by_status_row_index(grid: dict[str, Any]) -> dict[int, int]:
    """Map status row_band index to calendar year from structure year cells."""
    out: dict[int, int] = {}
    for row in grid.get("cells") or []:
        if not isinstance(row, list):
            continue
        year_cell = next(
            (cell for cell in row if isinstance(cell, dict) and cell.get("role") == "year"),
            None,
        )
        status_cell = next(
            (cell for cell in row if isinstance(cell, dict) and cell.get("role") == "status"),
            None,
        )
        if year_cell is None or status_cell is None:
            continue
        text = str(year_cell.get("text") or "").strip()
        if not _YEAR_RE.match(text):
            continue
        row_idx = int(status_cell.get("row_index") or year_cell.get("row_index") or 0)
        out[row_idx] = int(text)
    return out


def records_from_micro_grid_dict(grid: dict[str, Any]) -> list[dict[str, Any]]:
    """Project finance repayment records from a persisted micro_grid structure."""
    if not isinstance(grid, dict):
        return []
    page = int(grid.get("page") or 0)
    grid_id = str(grid.get("grid_id") or f"mg_p{page}_repayment_0")
    date_range = _date_range_from_grid(grid)
    if date_range is None:
        return []
    start_year, start_month, end_year, end_month = date_range
    valid_months = set(_months_between(start_year, start_month, end_year, end_month))

    col_map: dict[int, int] = {}
    for band in grid.get("col_bands") or []:
        if not isinstance(band, dict):
            continue
        header = str(band.get("header") or "").strip()
        if header.isdigit():
            col_map[int(band.get("index") or 0)] = int(header)

    status_rows: list[list[dict[str, Any]]] = []
    amount_rows: list[list[dict[str, Any]]] = []
    for row in grid.get("cells") or []:
        if not isinstance(row, list) or not row:
            continue
        roles = {str(cell.get("role") or "") for cell in row if isinstance(cell, dict)}
        if "status" in roles:
            status_rows.append([cell for cell in row if isinstance(cell, dict)])
        elif "overdue_amount" in roles:
            amount_rows.append([cell for cell in row if isinstance(cell, dict)])

    amount_by_col: dict[int, str] = {}
    for row in amount_rows:
        for cell in row:
            text = str(cell.get("text") or "").strip()
            if text:
                amount_by_col[int(cell.get("col_index") or 0)] = text

    years_by_row = _years_by_status_row_index(grid)
    records: list[dict[str, Any]] = []
    for status_row in status_rows:
        row_idx = next(
            (int(cell.get("row_index") or 0) for cell in status_row if str(cell.get("role") or "") == "status"),
            0,
        )
        row_year = years_by_row.get(row_idx)
        for cell in status_row:
            if str(cell.get("role") or "") != "status":
                continue
            col_idx = int(cell.get("col_index") or 0)
            month = col_map.get(col_idx)
            status = str(cell.get("text") or "").strip()
            if not month or not status:
                continue
            year = row_year
            if year is None:
                year = next((y for y, m in valid_months if m == month), None)
            if year is None or (year, month) not in valid_months:
                continue
            amount = amount_by_col.get(col_idx, "0") or "0"
            bbox = cell.get("bbox")
            record: dict[str, Any] = {
                "year": year,
                "month": month,
                "status": status,
                "overdue_amount": amount,
                "source_cell_refs": [
                    {
                        "page": page,
                        "grid_id": grid_id,
                        "row": cell.get("row_index"),
                        "col": month,
                    }
                ],
                "confidence": float(cell.get("confidence") or 0.7),
            }
            if isinstance(bbox, list) and len(bbox) == 4:
                record["status_bbox"] = list(bbox)
            records.append(record)
    return records


def dedupe_repayment_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one record per (grid_id, year, month), preferring higher confidence."""
    best: dict[tuple[str, int, int], dict[str, Any]] = {}
    order: list[tuple[str, int, int]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        refs = record.get("source_cell_refs") or [{}]
        grid_id = str((refs[0] or {}).get("grid_id") or "")
        key = (grid_id, int(record.get("year") or 0), int(record.get("month") or 0))
        if key not in best:
            order.append(key)
            best[key] = record
            continue
        if float(record.get("confidence") or 0.0) > float(best[key].get("confidence") or 0.0):
            best[key] = record
    return [best[key] for key in order]
