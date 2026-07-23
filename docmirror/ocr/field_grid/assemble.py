# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Cell assembly and in-column continuation merge."""

from __future__ import annotations

import re
from typing import Any

from docmirror.layout.profile.registry import load_table_semantics
from docmirror.ocr.field_grid.assign import (
    assign_tokens_to_col_bands,
    assignment_confidence,
    assignment_method,
    cell_bbox,
)
from docmirror.ocr.field_grid.bands import union_cell_bbox
from docmirror.ocr.field_grid.models import FieldCell
from docmirror.ocr.field_grid.type_gate import apply_type_gate, infer_types
from docmirror.ocr.micro_grid.models import OCRToken

_DATE_IN_TEXT = re.compile(r"\d{4}[./-]\d{1,2}[./-]\d{1,2}")
_CURRENCY_IN_TEXT = re.compile(r"人民币|美元|欧元|日元|港币")
_AMOUNT_COMMA = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?")
_AMOUNT_PLAIN = re.compile(r"(?<!\d)\d{4,}(?:\.\d+)?(?!\d)")
_COMPACT_DATE = re.compile(r"(?<!\d)\d{8}(?!\d)")
_FIELD_GRID_SEMANTICS = load_table_semantics().get("field_grid") or {}
LABEL_TYPE_HINTS: dict[str, tuple[str, ...]] = {
    str(label): tuple(str(value) for value in values)
    for label, values in (_FIELD_GRID_SEMANTICS.get("label_type_hints") or {}).items()
}


def _label_type_hint(label_text: str) -> tuple[str, ...]:
    compact = re.sub(r"\s+", "", label_text or "")
    for key, hints in LABEL_TYPE_HINTS.items():
        if key in compact:
            return hints
    return ("text",)


def _extract_semantic_spans(text: str) -> list[tuple[int, int, str, str]]:
    """Non-overlapping semantic spans from a possibly merged OCR line."""
    if not text.strip():
        return []
    occupied: list[tuple[int, int]] = []
    spans: list[tuple[int, int, str, str]] = []

    def _take(start: int, end: int, value: str, kind: str) -> None:
        if any(not (end <= s or start >= e) for s, e in occupied):
            return
        occupied.append((start, end))
        spans.append((start, end, value, kind))

    for match in _DATE_IN_TEXT.finditer(text):
        _take(match.start(), match.end(), match.group(0), "date")

    dotted_dates = {re.sub(r"[./-]", "", span[2]) for span in spans if span[3] == "date"}
    for match in _COMPACT_DATE.finditer(text):
        if match.group(0) in dotted_dates:
            occupied.append((match.start(), match.end()))

    for match in _CURRENCY_IN_TEXT.finditer(text):
        _take(match.start(), match.end(), match.group(0), "currency")

    comma_matches = [
        match
        for match in _AMOUNT_COMMA.finditer(text)
        if not any(not (match.end() <= s or match.start() >= e) for s, e in occupied)
    ]
    if comma_matches:
        match = comma_matches[-1]
        val = match.group(0)
        suffix = re.search(r"(\d{2},\d{3})$", val)
        if suffix:
            val = suffix.group(1)
            start = match.end() - len(val)
            _take(start, match.end(), val, "amount")
        else:
            _take(match.start(), match.end(), val, "amount")
    elif not dotted_dates:
        for match in _AMOUNT_PLAIN.finditer(text):
            val = match.group(0)
            if val.replace(".", "").isdigit() and len(val.replace(".", "")) >= 4:
                _take(match.start(), match.end(), val, "amount")

    spans.sort(key=lambda item: item[0])
    return spans


def line_has_mixed_semantics(text: str) -> bool:
    spans = _extract_semantic_spans(text)
    kinds = {kind for *_rest, kind in spans}
    return len(kinds) >= 2


def split_line_into_semantic_tokens(line: dict[str, Any], *, page: int, prefix: str) -> list[OCRToken]:
    """Split a merged OCR value line into semantic chunks with approximate bboxes."""
    text = line["text"]
    spans = _extract_semantic_spans(text)
    kinds = {kind for *_rest, kind in spans}
    if len(kinds) < 2:
        return []

    x0, y0, x1, y1 = line["bbox"]
    width = max(x1 - x0, 1.0)
    total = max(len(text), 1)
    tokens: list[OCRToken] = []
    for idx, (start, end, part, kind) in enumerate(spans):
        tokens.append(
            OCRToken(
                token_id=f"{prefix}_sem_{line['line_id']}_{idx}",
                text=part,
                bbox=(x0 + width * (start / total), y0, x0 + width * (end / total), y1),
                confidence=line.get("confidence", 1.0),
                page=page,
                source=f"semantic_line_split:{kind}",
            )
        )
    return tokens


def route_semantic_tokens_to_bands(
    semantic_tokens: list[OCRToken],
    col_bands: list[dict[str, Any]],
) -> dict[int, list[OCRToken]]:
    """Assign semantic tokens to columns by label type, then by x proximity."""
    out: dict[int, list[OCRToken]] = {int(b["index"]): [] for b in col_bands}
    used: set[str] = set()

    for token in semantic_tokens:
        kind = "text"
        if ":" in token.source:
            kind = token.source.rsplit(":", 1)[-1]
        else:
            inferred = infer_types(token.text)
            if "date" in inferred:
                kind = "date"
            elif "currency" in inferred:
                kind = "currency"
            elif "amount" in inferred:
                kind = "amount"

        type_candidates = [band for band in col_bands if kind in _label_type_hint(str(band.get("header") or ""))]
        pool = type_candidates or col_bands
        best_band: dict[str, Any] | None = None
        best_dist = float("inf")
        cx = token.center[0]
        for band in pool:
            bbox = band["bbox"]
            center = (float(bbox[0]) + float(bbox[2])) / 2.0
            dist = abs(cx - center)
            if dist < best_dist and int(band["index"]) not in {
                int(b["index"]) for b in type_candidates if out[int(b["index"])]
            }:
                best_band = band
                best_dist = dist
        if best_band is None:
            for band in pool:
                center = (float(band["bbox"][0]) + float(band["bbox"][2])) / 2.0
                dist = abs(cx - center)
                if dist < best_dist:
                    best_band = band
                    best_dist = dist
        if best_band is not None and token.token_id not in used:
            out[int(best_band["index"])].append(token)
            used.add(token.token_id)
    return out


def score_cell_for_label(cell: FieldCell, label_text: str) -> float:
    hints = _label_type_hint(label_text)
    score = float(len(cell.text or ""))
    if cell.geometry_status == "quarantined":
        return -1.0
    if any(h in cell.inferred_types for h in hints):
        score += 1000.0
    if "text" in hints and "long_id" in hints and "long_id" in cell.inferred_types:
        score += 500.0
    return score


def value_row_band_from_line(line: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": 0,
        "bbox": list(line["bbox"]),
        "role": "value",
        "source_line_id": line["line_id"],
    }


def assemble_cell_text(tokens: list[OCRToken]) -> str:
    return "".join(token.text for token in sorted(tokens, key=lambda t: (t.bbox[1], t.bbox[0]))).strip()


def build_field_cell(
    *,
    cell_id: str,
    row_band: dict[str, Any],
    col_band: dict[str, Any],
    tokens: list[OCRToken],
    line_ids: tuple[str, ...] = (),
    label_text: str | None = None,
    assignment_method_override: str | None = None,
) -> FieldCell:
    text = assemble_cell_text(tokens)
    method = assignment_method_override or assignment_method(tokens)
    assign_conf = assignment_confidence(tokens, row_band, col_band)
    geometry_status = "exact" if text and method == "overlap:native_token" else ("estimated" if text else "empty")
    cell = FieldCell(
        cell_id=cell_id,
        row_index=int(row_band["index"]),
        col_index=int(col_band["index"]),
        label_text=label_text or str(col_band.get("header") or ""),
        text=text,
        raw_text=text,
        bbox=cell_bbox(row_band, col_band),
        token_ids=tuple(t.token_id for t in tokens),
        line_ids=line_ids,
        confidence=max((t.confidence for t in tokens), default=0.0),
        assignment_confidence=assign_conf,
        assignment_method=method,
        geometry_status=geometry_status,
    )
    return apply_type_gate(cell)


def _line_char_tokens(line: dict[str, Any], col_band: dict[str, Any], *, page: int, prefix: str) -> list[OCRToken]:
    from docmirror.ocr.field_grid.tokens import expand_tokens_to_char_tokens

    text = line["text"]
    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return []
    x0, y0, x1, y1 = line["bbox"]
    width = max(x1 - x0, 1.0)
    step = width / len(chars)
    raw_tokens = [
        OCRToken(
            token_id=f"{prefix}_{line['line_id']}_c{i}",
            text=ch,
            bbox=(x0 + step * i, y0, x0 + step * (i + 1), y1),
            confidence=line.get("confidence", 1.0),
            page=page,
            source="line_char_split",
        )
        for i, ch in enumerate(chars)
    ]
    row_band = value_row_band_from_line(line)
    return assign_tokens_to_col_bands(expand_tokens_to_char_tokens(raw_tokens), row_band, [col_band]).get(
        int(col_band["index"]), []
    )


def _compact_merge_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _should_not_merge_continuation(left: str, right: str, *, min_overlap: int = 4) -> bool:
    """Skip merges where OCR duplicated a long prefix into the next fragment."""
    left_c = _compact_merge_text(left)
    right_c = _compact_merge_text(right)
    if len(right_c) < min_overlap or len(left_c) < min_overlap:
        return False
    if left_c.endswith(right_c[: max(min_overlap, len(right_c) // 2)]):
        return True
    if right_c.startswith(left_c[-min(len(left_c), 10) :]):
        return True
    return False


def merge_in_column_continuations(
    fragments: list[FieldCell],
    *,
    max_y_gap: float = 22.0,
) -> list[FieldCell]:
    """Merge cell fragments within the same column band only."""
    if not fragments:
        return []

    by_key: dict[str, list[FieldCell]] = {}
    for cell in fragments:
        key = f"{cell.col_index}:{cell.label_text or ''}"
        by_key.setdefault(key, []).append(cell)

    merged: list[FieldCell] = []
    for key in sorted(by_key):
        col_cells = sorted(by_key[key], key=lambda c: c.bbox[1])
        col_idx = col_cells[0].col_index
        if not col_cells:
            continue

        current = col_cells[0]
        chain_ids: list[str] = []

        for nxt in col_cells[1:]:
            y_gap = nxt.bbox[1] - current.bbox[3]
            row_h = max(current.bbox[3] - current.bbox[1], 1.0)
            if y_gap > max(max_y_gap, row_h * 1.8):
                merged.append(current)
                current = nxt
                chain_ids = []
                continue
            if nxt.geometry_status == "quarantined":
                merged.append(current)
                current = nxt
                chain_ids = []
                continue
            if _should_not_merge_continuation(current.text, nxt.text):
                merged.append(current)
                current = nxt
                chain_ids = []
                continue
            if current.inferred_types != nxt.inferred_types and "text" not in current.inferred_types:
                merged.append(current)
                current = nxt
                chain_ids = []
                continue

            combined_text = current.text + nxt.text
            chain_ids.append(nxt.cell_id)
            current = FieldCell(
                cell_id=current.cell_id,
                row_index=current.row_index,
                col_index=col_idx,
                label_text=current.label_text,
                text=combined_text,
                raw_text=combined_text,
                bbox=union_cell_bbox([current.bbox, nxt.bbox]),
                token_ids=current.token_ids + nxt.token_ids,
                line_ids=current.line_ids + nxt.line_ids,
                confidence=min(current.confidence, nxt.confidence),
                assignment_confidence=min(current.assignment_confidence, nxt.assignment_confidence),
                assignment_method=current.assignment_method,
                geometry_status=current.geometry_status if current.text else nxt.geometry_status,
                inferred_types=current.inferred_types,
                quarantine_reason=current.quarantine_reason or nxt.quarantine_reason,
                continuation_cell_ids=tuple(chain_ids),
                audit={**current.audit, "merged_fragments": len(chain_ids) + 1},
            )
            current = apply_type_gate(current)

        merged.append(current)

    return merged
