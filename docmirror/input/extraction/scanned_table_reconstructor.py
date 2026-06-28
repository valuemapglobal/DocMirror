# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Conservative table reconstruction for OCR-only scanned statement pages."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from typing import Any

from docmirror.models.entities.domain import Block

_FINANCIAL_KEYWORDS = (
    "资产负债表",
    "利润表",
    "现金流量表",
    "所有者权益变动表",
    "年末余额",
    "年初余额",
    "本年发生额",
    "上年发生额",
    "金额单位",
)
_FINANCIAL_HEADER_LABELS = {
    "项目",
    "附注",
    "年末余额",
    "年初余额",
    "本年发生额",
    "上年发生额",
}
_NOISE_TEXT = {"英", "超", "江", "都", "华", "盖", "身", "品", "凯", "单", "A", "E", "H", "ZV"}
_NUMBER_RE = re.compile(r"\d[\d,，]*(?:\.\d+)?")
_SHORT_NOISE_RE = re.compile(r"^[A-Za-z0-9]{1,3}$")


@dataclass(frozen=True)
class _Token:
    text: str
    bbox: tuple[float, float, float, float]
    evidence_id: str
    confidence: float

    @property
    def cx(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2.0

    @property
    def cy(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2.0

    @property
    def h(self) -> float:
        return max(1.0, self.bbox[3] - self.bbox[1])


@dataclass
class _Row:
    tokens: list[_Token]

    @property
    def cy(self) -> float:
        return statistics.median(token.cy for token in self.tokens)

    @property
    def h(self) -> float:
        return statistics.median(token.h for token in self.tokens)

    @property
    def text(self) -> str:
        return " ".join(token.text for token in sorted(self.tokens, key=lambda t: t.bbox[0])).strip()


def reconstruct_scanned_statement_table(
    blocks: list[Block],
    *,
    page_number: int,
    page_width: float,
    page_height: float,
    start_order: int = 0,
) -> Block | None:
    """Build one page-level table block from OCR tokens when geometry is strong.

    This is intentionally conservative. It targets scanned financial statement
    pages where OCR has produced token-level boxes but the native PDF table
    extractor has no vector/text layer to work with.
    """
    if any(block.block_type == "table" for block in blocks):
        return None
    tokens = [_block_to_token(block) for block in blocks]
    tokens = [token for token in tokens if token is not None and _is_useful_token(token)]
    if len(tokens) < 12:
        return None
    page_text = " ".join(token.text for token in tokens)
    numeric_count = sum(1 for token in tokens if _looks_numeric(token.text))
    keyword_hits = sum(1 for keyword in _FINANCIAL_KEYWORDS if keyword in page_text)
    if keyword_hits == 0 and numeric_count < 12:
        return None

    rows = _cluster_rows(tokens)
    header_index = _find_header_row(rows)
    if header_index is None:
        return None
    table_rows = _trim_table_rows(rows[header_index:])
    if len(table_rows) < 4:
        return None

    header_tokens = _normalize_header_tokens(table_rows[0].tokens)
    anchors = _column_anchors(header_tokens, tokens)
    if len(anchors) < 3:
        return None

    raw, cell_bboxes, cell_evidence_ids, cell_confidences = _materialize_rows(table_rows, anchors)
    if len(raw) < 4 or max((len(row) for row in raw), default=0) < 3:
        return None
    if _non_empty_cells(raw[1:]) < 8:
        return None

    bbox = _union_bbox([token.bbox for row in table_rows for token in row.tokens])
    geometry = {
        "geometry_source": "scanned_ocr_statement_grid",
        "geometry_confidence": _grid_confidence(raw, keyword_hits=keyword_hits),
        "coordinate_system": "pdf_points_top_left",
        "cell_bboxes": cell_bboxes,
        "cell_geometry_status": [
            ["exact" if cell else "missing" for cell in row]
            for row in raw
        ],
        "cell_geometry_loss_reason": [
            [None if cell else "empty_ocr_cell" for cell in row]
            for row in raw
        ],
        "cell_evidence_ids": cell_evidence_ids,
        "cell_token_ids": cell_evidence_ids,
        "cell_confidences": cell_confidences,
        "row_bands": _row_bands(table_rows),
        "col_bands": _col_bands(anchors, bbox),
    }
    orientation_attrs = _ocr_orientation_attrs(blocks)
    block_id = f"scanned_table:p{page_number:04d}:0000"
    return Block(
        block_id=block_id,
        block_type="table",
        bbox=bbox,
        reading_order=start_order,
        page=page_number,
        raw_content=raw,
        attrs={
            "extraction_layer": "scanned_ocr_statement_grid",
            "extraction_confidence": geometry["geometry_confidence"],
            "geometry": geometry,
            "role": "financial_statement",
            "preserve_headers": True,
            "statement_keywords": [kw for kw in _FINANCIAL_KEYWORDS if kw in page_text],
            "source": "scanned_table_reconstructor",
            "page_width": page_width,
            "page_height": page_height,
            **orientation_attrs,
        },
        evidence_ids=tuple(sorted({eid for row in cell_evidence_ids for cell in row for eid in cell})),
    )


def _block_to_token(block: Block) -> _Token | None:
    text = str(block.raw_content or "").strip()
    if not text:
        return None
    bbox = tuple(float(v) for v in (block.bbox or (0.0, 0.0, 0.0, 0.0)))
    if len(bbox) != 4 or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    confidence = float((block.attrs or {}).get("confidence") or 1.0)
    evidence_ids = list(block.evidence_ids or ())
    return _Token(text=text, bbox=bbox, evidence_id=evidence_ids[0] if evidence_ids else block.block_id, confidence=confidence)


def _ocr_orientation_attrs(blocks: list[Block]) -> dict[str, Any]:
    """Summarize page-level OCR orientation metadata from source token blocks."""
    rotations: dict[int, int] = {}
    scores: list[float] = []
    normalized_width: float | None = None
    normalized_height: float | None = None
    for block in blocks:
        attrs = block.attrs or {}
        if "ocr_rotation" in attrs:
            try:
                rotation = int(attrs["ocr_rotation"]) % 360
            except (TypeError, ValueError):
                rotation = 0
            rotations[rotation] = rotations.get(rotation, 0) + 1
        if attrs.get("ocr_orientation_score") is not None:
            try:
                scores.append(float(attrs["ocr_orientation_score"]))
            except (TypeError, ValueError):
                pass
        if normalized_width is None and attrs.get("normalized_page_width") is not None:
            try:
                normalized_width = float(attrs["normalized_page_width"])
            except (TypeError, ValueError):
                normalized_width = None
        if normalized_height is None and attrs.get("normalized_page_height") is not None:
            try:
                normalized_height = float(attrs["normalized_page_height"])
            except (TypeError, ValueError):
                normalized_height = None

    out: dict[str, Any] = {}
    if rotations:
        out["ocr_rotation"] = max(rotations.items(), key=lambda item: (item[1], -item[0]))[0]
    if scores:
        out["ocr_orientation_score"] = max(scores)
    if normalized_width is not None:
        out["normalized_page_width"] = normalized_width
    if normalized_height is not None:
        out["normalized_page_height"] = normalized_height
    return out


def _is_useful_token(token: _Token) -> bool:
    text = token.text.strip()
    if not text:
        return False
    if text in _NOISE_TEXT:
        return False
    if len(text) == 1 and not text.isdigit() and text not in {"项", "目"}:
        return False
    return True


def _looks_numeric(text: str) -> bool:
    return bool(_NUMBER_RE.search(text.replace("，", ",")))


def _cluster_rows(tokens: list[_Token]) -> list[_Row]:
    rows: list[_Row] = []
    for token in sorted(tokens, key=lambda item: (item.cy, item.bbox[0])):
        placed = False
        for row in rows[-5:]:
            tolerance = max(4.0, min(12.0, max(row.h, token.h) * 0.65))
            if abs(token.cy - row.cy) <= tolerance:
                row.tokens.append(token)
                placed = True
                break
        if not placed:
            rows.append(_Row(tokens=[token]))
    for row in rows:
        row.tokens.sort(key=lambda item: item.bbox[0])
    return rows


def _find_header_row(rows: list[_Row]) -> int | None:
    best_index: int | None = None
    best_score = 0
    for index, row in enumerate(rows[:16]):
        text = row.text
        score = 0
        if "年末余额" in text or "年初余额" in text:
            score += 4
        if "本年发生额" in text or "上年发生额" in text:
            score += 4
        if "附注" in text:
            score += 2
        if "项" in text and "目" in text:
            score += 2
        if len(row.tokens) >= 3:
            score += 1
        if score > best_score:
            best_score = score
            best_index = index
    return best_index if best_score >= 4 else None


def _trim_table_rows(rows: list[_Row]) -> list[_Row]:
    trimmed: list[_Row] = []
    blankish_streak = 0
    for row in rows:
        text = row.text
        has_signal = (
            len(row.tokens) >= 2
            or _looks_numeric(text)
            or any(keyword in text for keyword in _FINANCIAL_KEYWORDS)
            or any(_is_cjk(char) for char in text)
        )
        if has_signal:
            blankish_streak = 0
            trimmed.append(row)
            continue
        blankish_streak += 1
        if blankish_streak >= 3 and len(trimmed) >= 4:
            break
        trimmed.append(row)
    return trimmed


def _normalize_header_tokens(tokens: list[_Token]) -> list[_Token]:
    useful = [token for token in tokens if token.text not in _NOISE_TEXT]
    out: list[_Token] = []
    i = 0
    while i < len(useful):
        token = useful[i]
        if token.text == "项" and i + 1 < len(useful) and useful[i + 1].text == "目":
            nxt = useful[i + 1]
            out.append(
                _Token(
                    text="项目",
                    bbox=_union_bbox([token.bbox, nxt.bbox]),
                    evidence_id=f"{token.evidence_id}|{nxt.evidence_id}",
                    confidence=min(token.confidence, nxt.confidence),
                )
            )
            i += 2
            continue
        if token.text in {"项", "目"}:
            out.append(
                _Token(
                    text="项目",
                    bbox=token.bbox,
                    evidence_id=token.evidence_id,
                    confidence=token.confidence,
                )
            )
            i += 1
            continue
        out.append(token)
        i += 1
    return [
        token
        for token in out
        if token.text in _FINANCIAL_HEADER_LABELS or not _SHORT_NOISE_RE.fullmatch(token.text)
    ]


def _column_anchors(header_tokens: list[_Token], all_tokens: list[_Token]) -> list[tuple[float, str]]:
    anchors = [(token.cx, token.text) for token in header_tokens if token.text.strip()]
    anchors = [(x, text) for x, text in anchors if text not in _NOISE_TEXT]
    if len(anchors) >= 3:
        return sorted(anchors, key=lambda item: item[0])
    xs = sorted(token.cx for token in all_tokens)
    if len(xs) < 12:
        return []
    clusters: list[list[float]] = [[xs[0]]]
    gaps = [b - a for a, b in zip(xs, xs[1:]) if b > a]
    median_gap = statistics.median(gaps) if gaps else 16.0
    threshold = max(36.0, median_gap * 3.0)
    for x in xs[1:]:
        if x - clusters[-1][-1] > threshold:
            clusters.append([x])
        else:
            clusters[-1].append(x)
    centers = [statistics.median(cluster) for cluster in clusters if len(cluster) >= 2]
    return [(center, f"col_{index + 1}") for index, center in enumerate(centers)]


def _materialize_rows(
    rows: list[_Row],
    anchors: list[tuple[float, str]],
) -> tuple[list[list[str]], list[list[list[float] | None]], list[list[list[str]]], list[list[float | None]]]:
    centers = [x for x, _label in anchors]
    labels = [label for _x, label in anchors]
    col_count = len(centers)
    raw: list[list[str]] = []
    bboxes: list[list[list[float] | None]] = []
    evidence_ids: list[list[list[str]]] = []
    confidences: list[list[float | None]] = []
    for row_index, row in enumerate(rows):
        buckets: list[list[_Token]] = [[] for _ in range(col_count)]
        for token in row.tokens:
            col_index = _nearest_column(token.cx, centers)
            buckets[col_index].append(token)
        if row_index == 0:
            texts = labels
        else:
            texts = [_join_cell_tokens(bucket) for bucket in buckets]
        raw.append(texts)
        bboxes.append([_union_bbox([token.bbox for token in bucket]) if bucket else None for bucket in buckets])
        evidence_ids.append([[part for token in bucket for part in token.evidence_id.split("|") if part] for bucket in buckets])
        confidences.append([
            round(sum(token.confidence for token in bucket) / len(bucket), 4) if bucket else None
            for bucket in buckets
        ])
    return raw, bboxes, evidence_ids, confidences


def _nearest_column(x: float, centers: list[float]) -> int:
    return min(range(len(centers)), key=lambda index: abs(x - centers[index]))


def _join_cell_tokens(tokens: list[_Token]) -> str:
    parts = [token.text for token in sorted(tokens, key=lambda item: item.bbox[0])]
    text = ""
    for part in parts:
        if not text:
            text = part
            continue
        if text[-1].isdigit() and part[0].isdigit():
            text += part
        elif _is_cjk(text[-1]) or _is_cjk(part[0]):
            text += part
        else:
            text += " " + part
    return text.strip()


def _is_cjk(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff"


def _non_empty_cells(rows: list[list[str]]) -> int:
    return sum(1 for row in rows for cell in row if str(cell or "").strip())


def _grid_confidence(raw: list[list[str]], *, keyword_hits: int) -> float:
    populated = _non_empty_cells(raw)
    total = sum(len(row) for row in raw) or 1
    density = populated / total
    numeric_rows = sum(1 for row in raw[1:] if any(_looks_numeric(cell) for cell in row))
    score = 0.55 + min(0.2, density * 0.2) + min(0.15, numeric_rows / max(1, len(raw) - 1) * 0.15)
    if keyword_hits:
        score += 0.08
    return round(min(0.92, score), 4)


def _row_bands(rows: list[_Row]) -> list[dict[str, Any]]:
    bands: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        bbox = _union_bbox([token.bbox for token in row.tokens])
        bands.append({"index": index, "bbox": list(bbox), "y0": bbox[1], "y1": bbox[3]})
    return bands


def _col_bands(anchors: list[tuple[float, str]], table_bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    centers = [x for x, _label in anchors]
    labels = [label for _x, label in anchors]
    dividers = [table_bbox[0]]
    for left, right in zip(centers, centers[1:]):
        dividers.append((left + right) / 2.0)
    dividers.append(table_bbox[2])
    return [
        {
            "index": index,
            "header": labels[index],
            "bbox": [dividers[index], table_bbox[1], dividers[index + 1], table_bbox[3]],
            "x0": dividers[index],
            "x1": dividers[index + 1],
        }
        for index in range(len(labels))
    ]


def _union_bbox(bboxes: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    if not bboxes:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        min(bbox[0] for bbox in bboxes),
        min(bbox[1] for bbox in bboxes),
        max(bbox[2] for bbox in bboxes),
        max(bbox[3] for bbox in bboxes),
    )
