# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Universal scanned OCR — generic OCR extraction without table assumptions.

Purpose: Detects table presence, groups OCR words into lines, and extracts
universal text/table content for mixed scanned layouts.

Main components: ``ocr_extract_universal``, ``_group_words_into_lines``.

Upstream: OCR word stream from ``runner``.

Downstream: ``ocr.scanned.analyze_page``, text block assembly.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

from docmirror.ocr.micro_grid.models import OCRToken, TieredTokenCollection
from docmirror.ocr.preprocess.pipeline import _render_page_to_bgr
from docmirror.ocr.recognize.runner import _run_ocr
from docmirror.ocr.reconstruct.grid import _detect_table_lines_hough
from docmirror.ocr.scanned.analyze_page import analyze_scanned_page


def _detect_has_table(img, page_h: int) -> bool:
    """Check whether the page image has genuine table line structure.

    Rejects decorative border frames by verifying that detected columns
    have comparable widths (widest / median ≤ 5).
    """
    col_bounds = _detect_table_lines_hough(img, page_h, img.shape[1] if img is not None else 0)
    if not col_bounds or len(col_bounds) < 3:
        return False

    # Reject border-frame false positives: in a real table, columns
    # have roughly comparable widths.  A frame has very narrow border
    # columns flanking one huge content area.
    widths = sorted(b - a for a, b in col_bounds)
    median_w = widths[len(widths) // 2]
    max_w = widths[-1]
    if median_w > 0 and max_w / median_w > 5:
        return False

    return True


def _group_words_into_lines(words: list[tuple], y_tolerance: float = 12.0) -> list[dict]:
    """Group OCR words into text lines by y-proximity.

    Returns a list of line dicts sorted in reading order, each with:
        {"text": str, "bbox": (x0, y0, x1, y1)}
    """
    if not words:
        return []

    # Sort by y, then x
    sorted_w = sorted(words, key=lambda w: (w[1], w[0]))

    lines: list[dict] = []
    cur_words = [sorted_w[0]]
    cur_y = sorted_w[0][1]

    for w in sorted_w[1:]:
        if abs(w[1] - cur_y) <= y_tolerance:
            cur_words.append(w)
        else:
            # Finish current line
            cur_words.sort(key=lambda ww: ww[0])
            text = " ".join(ww[4] for ww in cur_words)
            x0 = min(ww[0] for ww in cur_words)
            y0 = min(ww[1] for ww in cur_words)
            x1 = max(ww[2] for ww in cur_words)
            y1 = max(ww[3] for ww in cur_words)
            lines.append({"text": text, "bbox": (x0, y0, x1, y1)})
            cur_words = [w]
            cur_y = w[1]

    # Last line
    if cur_words:
        cur_words.sort(key=lambda ww: ww[0])
        text = " ".join(ww[4] for ww in cur_words)
        x0 = min(ww[0] for ww in cur_words)
        y0 = min(ww[1] for ww in cur_words)
        x1 = max(ww[2] for ww in cur_words)
        y1 = max(ww[3] for ww in cur_words)
        lines.append({"text": text, "bbox": (x0, y0, x1, y1)})

    return lines


def _words_to_ocr_tokens(words: list[tuple], *, page_idx: int) -> list[OCRToken]:
    """Convert RapidOCR word tuples to OCRToken objects using the universal factory.

    Returns OCRToken objects so downstream consumers get rich typed data
    with bbox, confidence, source tracking, and confidence_tier.
    Call .to_dict() when serialization is needed.
    """
    tokens: list[OCRToken] = []
    for idx, word in enumerate(words or []):
        try:
            token = OCRToken.from_rapidocr_word(word, page=page_idx + 1, source="rapidocr", idx=idx)
            tokens.append(token)
        except (ValueError, TypeError):
            continue
    return tokens


def _correct_general_words(
    words: list[tuple],
    *,
    page_idx: int,
    mode: str = "safe",
    domain: str | None = None,
    language: str | None = None,
    country: str | None = None,
    locale: str | None = None,
    pack_ids: tuple[str, ...] = (),
) -> tuple[list[tuple], dict[str, Any]]:
    from docmirror.ocr.correction import CorrectionContext, SafeOCRCorrector

    corrector = SafeOCRCorrector()
    corrected: list[tuple] = []
    events: list[dict[str, Any]] = []
    for index, word in enumerate(words or []):
        if len(word) < 5:
            corrected.append(word)
            continue
        try:
            confidence = OCRToken.from_rapidocr_word(word, page=page_idx + 1, idx=index).confidence
        except (TypeError, ValueError):
            confidence = None
        source_ref = f"ocr_p{page_idx + 1}_t{index}"
        decision = corrector.correct(
            str(word[4] or ""),
            CorrectionContext(
                role="text_line",
                domain=domain,
                source_ref=source_ref,
                ocr_confidence=confidence,
                mode=mode if mode in {"off", "safe", "suggest"} else "safe",
                language=language,
                country=country,
                locale=locale,
                pack_ids=pack_ids,
            ),
        )
        mutable = list(word)
        mutable[4] = decision.output_text
        corrected.append(tuple(mutable))
        if decision.action != "unchanged":
            events.append(decision.to_dict())
    return corrected, {
        "mode": mode,
        "rules_version": 1,
        "processed_count": len(corrected),
        "applied_count": sum(1 for event in events if event.get("action") == "applied"),
        "suggested_count": sum(1 for event in events if event.get("action") == "suggested"),
        "events": events,
    }


def _correct_table_result(
    result: dict[str, Any],
    *,
    page_idx: int,
    mode: str,
    domain: str | None,
    language: str | None,
    country: str | None,
    locale: str | None,
    pack_ids: tuple[str, ...],
) -> dict[str, Any]:
    from docmirror.ocr.correction import CorrectionContext, SafeOCRCorrector

    main = result.get("table")
    declared = result.get("tables")
    tables = list(declared) if isinstance(declared, list) and declared else ([main] if isinstance(main, list) else [])
    if not tables:
        return result
    try:
        main_index = next(index for index, table in enumerate(tables) if table == main)
    except StopIteration:
        main_index = max(range(len(tables)), key=lambda index: len(tables[index]))
    corrector = SafeOCRCorrector()
    corrected_tables: list[list[list[str]]] = []
    events: list[dict[str, Any]] = []
    processed_count = 0
    for table_index, table in enumerate(tables):
        corrected_rows = [list(row) for row in table]
        for row_index, row in enumerate(corrected_rows):
            for column_index, value in enumerate(row):
                text = str(value or "").strip()
                if not text or (row_index > 0 and column_index > 0):
                    continue
                processed_count += 1
                decision = corrector.correct(
                    text,
                    CorrectionContext(
                        role="table_header" if row_index == 0 else "field_label",
                        domain=domain,
                        source_ref=f"ocr:p{page_idx + 1}:t{table_index}:r{row_index}:c{column_index}",
                        mode=mode if mode in {"off", "safe", "suggest"} else "safe",
                        language=language,
                        country=country,
                        locale=locale,
                        pack_ids=pack_ids,
                    ),
                )
                row[column_index] = decision.output_text
                if decision.action != "unchanged":
                    event = decision.to_dict()
                    event["target"] = {
                        "kind": "table_cell",
                        "page": page_idx + 1,
                        "table": table_index,
                        "row": row_index,
                        "column": column_index,
                    }
                    events.append(event)
        corrected_tables.append(corrected_rows)
    result["table"] = corrected_tables[main_index]
    if isinstance(declared, list):
        result["tables"] = corrected_tables
    result["ocr_corrections"] = {
        "mode": mode,
        "rules_version": 1,
        "processed_count": processed_count,
        "applied_count": sum(event.get("action") == "applied" for event in events),
        "suggested_count": sum(event.get("action") == "suggested" for event in events),
        "events": events,
    }
    return result


def ocr_extract_universal(
    fitz_page,
    page_idx: int,
    min_confidence: float = 0.3,
    *,
    page_quality: int | None = None,
    external_ocr_threshold: int | None = None,
    external_ocr_provider: Callable[..., list[tuple] | dict[str, Any]] | None = None,
    ocr_correction_mode: str = "safe",
    correction_domain: str | None = None,
    correction_language: str | None = None,
    correction_country: str | None = None,
    correction_locale: str | None = None,
    correction_pack_ids: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    """Universal OCR extraction — auto-detects document type.

    When ``page_quality`` is below ``external_ocr_threshold`` and
    ``external_ocr_provider`` is set, delegates to the external provider
    instead of built-in OCR (for 99% recognition targets on very poor scans).

    For table-dominant pages, delegates to ``analyze_scanned_page``
    to preserve the stable table extraction contract.  For general documents (licenses,
    certificates, contracts, etc.), returns all text lines in reading
    order with real bounding boxes.

    Returns:
        dict with ``content_type`` ("table" or "general") plus:
        - table: same format as ``analyze_scanned_page``
        - general: ``{"lines": [{"text", "bbox"}, ...], "page_h", "page_w"}``
        Returns ``None`` on failure.
    """
    try:
        # ── External OCR handoff: quality too low for built-in ──
        if (
            page_quality is not None
            and external_ocr_threshold is not None
            and page_quality < external_ocr_threshold
            and external_ocr_provider is not None
        ):
            img_bgr, page_h, page_w = _render_page_to_bgr(fitz_page, dpi=200)
            try:
                out = external_ocr_provider(img_bgr, page_idx=page_idx, dpi=200, min_confidence=min_confidence)
            except Exception as e:
                logger.warning(f"[external_ocr] Provider failed on page {page_idx}: {e}")
                out = None
            if out is not None:
                if isinstance(out, dict) and out.get("content_type") in ("table", "general"):
                    if out.get("content_type") == "table":
                        from docmirror.ocr.ocr_postprocess import postprocess_ocr_result

                        postprocess_ocr_result(out)
                        _correct_table_result(
                            out,
                            page_idx=page_idx,
                            mode=ocr_correction_mode,
                            domain=correction_domain,
                            language=correction_language,
                            country=correction_country,
                            locale=correction_locale,
                            pack_ids=correction_pack_ids,
                        )
                    logger.info(f"[DocMirror] Page {page_idx} delegated to external OCR (quality={page_quality})")
                    return out
                if isinstance(out, list) and out:
                    # List of (x0,y0,x1,y1,text,conf) → continue with our pipeline
                    all_words, img = out, img_bgr
                    page_w = img.shape[1]
                    has_table = _detect_has_table(img, page_h)
                    if has_table:
                        table_words = list(all_words)
                        table_result = analyze_scanned_page(
                            fitz_page,
                            page_idx,
                            min_confidence,
                            pre_existing_words=table_words,
                            pre_existing_img=img,
                            pre_existing_page_h=page_h,
                        )
                        if table_result:
                            table_result["content_type"] = "table"
                            return _correct_table_result(
                                table_result,
                                page_idx=page_idx,
                                mode=ocr_correction_mode,
                                domain=correction_domain,
                                language=correction_language,
                                country=correction_country,
                                locale=correction_locale,
                                pack_ids=correction_pack_ids,
                            )
                    raw_tokens = _words_to_ocr_tokens(all_words, page_idx=page_idx)
                    corrected_words, correction_audit = _correct_general_words(
                        all_words,
                        page_idx=page_idx,
                        mode=ocr_correction_mode,
                        domain=correction_domain,
                        language=correction_language,
                        country=correction_country,
                        locale=correction_locale,
                        pack_ids=correction_pack_ids,
                    )
                    lines = _group_words_into_lines(corrected_words, y_tolerance=12.0)
                    return {
                        "content_type": "general",
                        "lines": lines,
                        "tokens": raw_tokens,
                        "ocr_corrections": correction_audit,
                        "_page_image": img,
                        "page_h": page_h,
                        "page_w": page_w,
                    }
            # External failed or returned invalid → fall through to built-in

        all_words, img, page_h = _run_ocr(fitz_page, min_confidence)
        if all_words is None:
            return None

        page_w = img.shape[1] if img is not None else 0

        # Decide: table or general?
        has_table = _detect_has_table(img, page_h)

        if has_table:
            # Pass pre-existing words to avoid duplicate OCR in analyze_scanned_page
            table_words = list(all_words)
            table_result = analyze_scanned_page(
                fitz_page,
                page_idx,
                min_confidence,
                pre_existing_words=table_words,
                pre_existing_img=img,
                pre_existing_page_h=page_h,
            )
            if table_result:
                table_result["content_type"] = "table"
                return _correct_table_result(
                    table_result,
                    page_idx=page_idx,
                    mode=ocr_correction_mode,
                    domain=correction_domain,
                    language=correction_language,
                    country=correction_country,
                    locale=correction_locale,
                    pack_ids=correction_pack_ids,
                )
            # If table pipeline fails, fall through to general

        # General document: output all text lines in reading order
        tokens_for_general = _words_to_ocr_tokens(all_words, page_idx=page_idx)
        corrected_words, correction_audit = _correct_general_words(
            all_words,
            page_idx=page_idx,
            mode=ocr_correction_mode,
            domain=correction_domain,
            language=correction_language,
            country=correction_country,
            locale=correction_locale,
            pack_ids=correction_pack_ids,
        )
        lines = _group_words_into_lines(corrected_words, y_tolerance=12.0)
        tiered_for_general = TieredTokenCollection.from_tokens(tokens_for_general)
        return {
            "content_type": "general",
            "lines": lines,
            "tokens": tokens_for_general,
            "low_confidence_tokens": [t.to_dict() for t in tiered_for_general.low],
            "ocr_corrections": correction_audit,
            "_tiered": tiered_for_general,
            "_page_image": img,
            "page_h": page_h,
            "page_w": page_w,
        }

    except Exception as e:
        logger.warning(f"[universal] OCR error on page {page_idx}: {e}")
        return None
