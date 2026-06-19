# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Column and row band estimation for field grids."""

from __future__ import annotations

import re
from typing import Any, Callable

from docmirror.core.ocr.field_grid.models import LabelToken
from docmirror.core.ocr.local_structure.utils import union_bbox
from docmirror.core.ocr.micro_grid.models import BBox, OCRToken

_LABEL_SUFFIX_RE = re.compile(r"(机构|标识|日期|币种|金额|种类|方式|状态|编号|名称|期限|频率|责任|类型|余额|用途|利率)")
_PAGE_FOOTER_RE = re.compile(r"第\d+页，共\d+页")
_STATUS_HINT_RE = re.compile(r"(账户状态|账户关闭日期|截至\d{4}年|结清|结消)")

_GENERIC_LABELS: tuple[str, ...] = (
    "管理机构",
    "账户标识",
    "开立日期",
    "账户币种",
    "到期日期",
    "借款金额",
    "业务种类",
    "担保方式",
    "账户状态",
    "账户关闭日期",
    "共同借款标志",
    "还款期数",
    "还款频率",
    "还款方式",
)


def _split_glued_label_text(text: str, bbox: BBox) -> list[tuple[str, BBox]]:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return []
    spans: list[tuple[int, int, str]] = []
    for label in sorted(_GENERIC_LABELS, key=len, reverse=True):
        start = 0
        while start < len(compact):
            pos = compact.find(label, start)
            if pos < 0:
                break
            spans.append((pos, pos + len(label), label))
            start = pos + len(label)
    if not spans:
        return [(text.strip(), bbox)] if text.strip() else []

    spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    kept: list[tuple[int, int, str]] = []
    for span in spans:
        if any(not (span[1] <= k[0] or span[0] >= k[1]) for k in kept):
            continue
        kept.append(span)
    kept.sort(key=lambda item: item[0])

    x0, y0, x1, y1 = bbox
    width = max(x1 - x0, 1.0)
    total = max(len(compact), 1)
    out: list[tuple[str, BBox]] = []
    for s0, s1, label in kept:
        out.append(
            (
                label,
                (
                    x0 + width * (s0 / total),
                    y0,
                    x0 + width * (s1 / total),
                    y1,
                ),
            )
        )
    return out


def is_page_footer(text: str) -> bool:
    return bool(_PAGE_FOOTER_RE.search(text.replace(" ", "")))


def is_status_line(text: str) -> bool:
    compact = text.replace(" ", "")
    return bool(_STATUS_HINT_RE.search(compact))


def _interpolate_label_segments(line: dict[str, Any]) -> list[tuple[str, BBox]]:
    text = line["text"]
    suffixes = list(_LABEL_SUFFIX_RE.finditer(text))
    if len(suffixes) > 1:
        x0, y0, x1, y1 = line["bbox"]
        width = max(x1 - x0, 1.0)
        text_len = max(len(text), 1)
        segments: list[tuple[str, BBox]] = []
        start = 0
        for match in suffixes:
            end = match.end()
            part = text[start:end].strip()
            if part:
                segments.append(
                    (
                        part,
                        (
                            x0 + width * (start / text_len),
                            y0,
                            x0 + width * (end / text_len),
                            y1,
                        ),
                    )
                )
            start = end
        return segments
    parts = [p for p in re.split(r"\s+", text.strip()) if p]
    if len(parts) <= 1:
        return [(text, line["bbox"])]
    x0, y0, x1, y1 = line["bbox"]
    total_chars = sum(max(len(p), 1) for p in parts)
    cursor = x0
    out: list[tuple[str, BBox]] = []
    width = max(x1 - x0, 1.0)
    for part in parts:
        part_w = width * (max(len(part), 1) / max(total_chars, 1))
        out.append((part, (cursor, y0, cursor + part_w, y1)))
        cursor += part_w
    return out


def _tokens_in_bbox(tokens: list[OCRToken], bbox: BBox, *, y_margin: float = 4.0) -> list[OCRToken]:
    x0, y0, x1, y1 = bbox
    return [
        token for token in tokens
        if x0 - 2.0 <= token.center[0] <= x1 + 2.0 and y0 - y_margin <= token.center[1] <= y1 + y_margin
    ]


def extract_label_tokens(
    label_lines: list[dict[str, Any]],
    tokens: list[OCRToken],
    *,
    label_suffix_re: re.Pattern[str] | None = None,
) -> list[LabelToken]:
    """Extract label tokens with x-centers from possibly glued label rows."""
    del label_suffix_re
    if not label_lines:
        return []

    sorted_lines = sorted(label_lines, key=lambda line: line["bbox"][1])
    merged: list[LabelToken] = []
    label_idx = 0

    for line in sorted_lines:
        line_tokens = _tokens_in_bbox(tokens, line["bbox"])
        segments: list[tuple[str, BBox, tuple[str, ...]]] = []

        if len(line_tokens) >= 1:
            for token in sorted(line_tokens, key=lambda t: t.bbox[0]):
                glued_parts = _split_glued_label_text(token.text, token.bbox)
                if len(glued_parts) >= 2:
                    for part_text, part_bbox in glued_parts:
                        if _LABEL_SUFFIX_RE.search(part_text):
                            part_tokens = _tokens_in_bbox(tokens, part_bbox) or (token,)
                            segments.append((part_text.strip(), part_bbox, tuple(t.token_id for t in part_tokens)))
                elif _LABEL_SUFFIX_RE.search(token.text):
                    segments.append((token.text.strip(), token.bbox, (token.token_id,)))

        if len(segments) < 2:
            glued = _split_glued_label_text(line["text"], line["bbox"])
            if len(glued) >= 2:
                for part_text, part_bbox in glued:
                    part_tokens = _tokens_in_bbox(tokens, part_bbox)
                    token_ids = tuple(t.token_id for t in part_tokens)
                    segments.append((part_text.strip(), part_bbox, token_ids))
            else:
                for part_text, part_bbox in _interpolate_label_segments(line):
                    if not _LABEL_SUFFIX_RE.search(part_text):
                        continue
                    part_tokens = _tokens_in_bbox(tokens, part_bbox)
                    token_ids = tuple(t.token_id for t in part_tokens)
                    segments.append((part_text.strip(), part_bbox, token_ids))

        for text, bbox, token_ids in segments:
            if not text:
                continue
            merged.append(
                LabelToken(
                    text=text,
                    bbox=bbox,
                    line_id=line["line_id"],
                    token_ids=token_ids,
                    confidence=line.get("confidence", 1.0),
                )
            )
            label_idx += 1

    if len(sorted_lines) > 1:
        heights = [line["bbox"][3] - line["bbox"][1] for line in sorted_lines]
        avg_h = sum(heights) / max(len(heights), 1)
        if sorted_lines[1]["bbox"][1] - sorted_lines[0]["bbox"][1] < avg_h * 1.3:
            merged = sorted(merged, key=lambda item: item.x_center)

    return merged


def _cluster_label_lines_by_row(label_lines: list[dict[str, Any]], *, y_threshold: float = 14.0) -> list[list[dict[str, Any]]]:
    if not label_lines:
        return []
    sorted_lines = sorted(label_lines, key=lambda line: line["bbox"][1])
    rows: list[list[dict[str, Any]]] = [[sorted_lines[0]]]
    for line in sorted_lines[1:]:
        prev = rows[-1][-1]
        if line["bbox"][1] - prev["bbox"][1] <= y_threshold:
            rows[-1].append(line)
        else:
            rows.append([line])
    return rows


def estimate_col_bands_from_label_rows(
    label_lines: list[dict[str, Any]],
    tokens: list[OCRToken],
    roi_bbox: BBox,
) -> list[dict[str, Any]]:
    """Build column bands respecting multi-row headers (each row defines its own x columns)."""
    rows = _cluster_label_lines_by_row(label_lines)
    all_bands: list[dict[str, Any]] = []
    offset = 0
    for row_idx, row_lines in enumerate(rows):
        label_tokens = extract_label_tokens(row_lines, tokens)
        if not label_tokens:
            continue
        bands = estimate_col_bands_from_labels(label_tokens, roi_bbox)
        for band in bands:
            band["index"] = offset + int(band["index"])
            band["header_row"] = row_idx
            band["label_y"] = min(token.bbox[1] for token in label_tokens)
            offset = max(offset, int(band["index"]) + 1)
        all_bands.extend(bands)
    return all_bands


def nearest_header_row_for_y(col_bands: list[dict[str, Any]], y: float) -> int:
    rows = sorted({int(b.get("header_row", 0)) for b in col_bands})
    if not rows:
        return 0
    best_row = rows[0]
    best_dist = float("inf")
    for row_idx in rows:
        row_bands = [b for b in col_bands if int(b.get("header_row", 0)) == row_idx]
        if not row_bands:
            continue
        label_y = float(row_bands[0].get("label_y") or row_bands[0]["bbox"][1])
        dist = abs(y - label_y)
        if dist < best_dist:
            best_dist = dist
            best_row = row_idx
    return best_row


def estimate_col_bands_from_labels(
    label_tokens: list[LabelToken],
    roi_bbox: BBox,
) -> list[dict[str, Any]]:
    """Build column bands from label x-centers."""
    if not label_tokens:
        return []

    sorted_labels = sorted(label_tokens, key=lambda t: t.x_center)
    y0 = min(token.bbox[1] for token in sorted_labels)
    y1 = max(token.bbox[3] for token in sorted_labels)
    bands: list[dict[str, Any]] = []

    for idx, label in enumerate(sorted_labels):
        left = roi_bbox[0] if idx == 0 else (sorted_labels[idx - 1].x_center + label.x_center) / 2.0
        right = roi_bbox[2] if idx == len(sorted_labels) - 1 else (label.x_center + sorted_labels[idx + 1].x_center) / 2.0
        bands.append(
            {
                "index": idx,
                "header": label.text,
                "bbox": [left, y0, right, y1],
                "role": "label_column",
                "label_token_id": label.line_id,
                "geometry_status": "estimated",
            }
        )
    return bands


def align_col_bands_across_structures(
    structures: list[dict[str, Any]],
    *,
    min_cluster_size: int = 2,
) -> None:
    """Refine col_bands on a page using median label x-centers across blocks."""
    clusters: dict[str, list[float]] = {}
    for structure in structures:
        for band in structure.get("col_bands") or []:
            header = str(band.get("header") or "").strip()
            if not header:
                continue
            bbox = band.get("bbox") or []
            if len(bbox) != 4:
                continue
            cx = (float(bbox[0]) + float(bbox[2])) / 2.0
            clusters.setdefault(header, []).append(cx)

    if not clusters:
        return

    median_x: dict[str, float] = {}
    for header, values in clusters.items():
        if len(values) >= min_cluster_size:
            sorted_vals = sorted(values)
            median_x[header] = sorted_vals[len(sorted_vals) // 2]

    for structure in structures:
        bands = structure.get("col_bands") or []
        if not bands:
            continue
        sorted_bands = sorted(bands, key=lambda b: (float(b["bbox"][0]) + float(b["bbox"][2])) / 2.0)
        for idx, band in enumerate(sorted_bands):
            header = str(band.get("header") or "").strip()
            if header in median_x:
                cx = median_x[header]
                left = structure["bbox"][0] if idx == 0 else (sorted_bands[idx - 1]["bbox"][0] + cx) / 2.0
                right = structure["bbox"][2] if idx == len(sorted_bands) - 1 else (cx + sorted_bands[idx + 1]["bbox"][0]) / 2.0
                y0, y1 = band["bbox"][1], band["bbox"][3]
                band["bbox"] = [left, y0, right, y1]
                band["geometry_status"] = "schema_aligned"


def classify_block_lines(
    block_lines: list[dict[str, Any]],
    *,
    is_label_line,
) -> dict[str, Any]:
    """Classify lines into anchor, label, value, and status roles."""
    if not block_lines:
        return {"anchor": None, "label_lines": [], "value_lines": [], "status_lines": []}

    anchor = block_lines[0]
    label_lines: list[dict[str, Any]] = []
    value_lines: list[dict[str, Any]] = []
    status_lines: list[dict[str, Any]] = []

    for line in block_lines[1:]:
        text = line["text"]
        if is_page_footer(text):
            continue
        if is_status_line(text):
            status_lines.append(line)
            continue
        if is_label_line(line):
            label_lines.append(line)
            continue
        value_lines.append(line)

    return {
        "anchor": anchor,
        "label_lines": label_lines,
        "value_lines": value_lines,
        "status_lines": status_lines,
    }


def segment_field_sections(
    block_lines: list[dict[str, Any]],
    *,
    is_label_line: Callable[[dict[str, Any]], bool],
) -> list[dict[str, Any]]:
    """Split a block into label/value sections (primary + secondary field groups)."""
    sections: list[dict[str, Any]] = []
    i = 1
    while i < len(block_lines):
        line = block_lines[i]
        if is_page_footer(line["text"]):
            break
        if is_status_line(line["text"]) and not is_label_line(line):
            i += 1
            continue
        if not is_label_line(line):
            i += 1
            continue
        label_lines: list[dict[str, Any]] = []
        while i < len(block_lines) and is_label_line(block_lines[i]):
            label_lines.append(block_lines[i])
            i += 1
        value_lines: list[dict[str, Any]] = []
        while i < len(block_lines):
            current = block_lines[i]
            if is_page_footer(current["text"]):
                break
            if is_status_line(current["text"]) and not is_label_line(current):
                if re.search(r"截至\d{4}年", current["text"].replace(" ", "")):
                    break
                value_lines.append(current)
                i += 1
                continue
            if is_label_line(current):
                break
            value_lines.append(current)
            i += 1
        if label_lines and value_lines:
            sections.append({"label_lines": label_lines, "value_lines": value_lines})
    return sections


def value_row_band(line: dict[str, Any], *, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "bbox": list(line["bbox"]),
        "role": "value",
        "source_line_id": line["line_id"],
        "geometry_status": "estimated",
    }


def union_cell_bbox(boxes: list[BBox]) -> BBox:
    return union_bbox(boxes)
