# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
CoreExtractor — orchestrates PDF → BaseResult extraction.

Purpose: Main extraction engine: opens PDFs, iterates pages, runs layout
segmentation, table extraction (layered tiers), OCR fallback for scanned
pages, logical table composition, and assembles frozen ``BaseResult``.

Main components: ``CoreExtractor``.

Upstream: ``entry.factory``, ``FitzEngine``, ``analyze.pre_analyzer``.

Downstream: ``input.bridge.parse_result_bridge`` and vNext MirrorCore.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, replace

# S2: Module-level alias — perf_counter avoids gettimeofday syscall
_clock = time.perf_counter
from pathlib import Path
from typing import Any

from docmirror.input.entry.exceptions import ExtractionError
from docmirror.layout.normalization.transform import invert_matrix, rotation_matrix
from docmirror.layout.vocabulary import _is_header_row
from docmirror.layout.watermark import preprocess_document
from docmirror.models.entities.domain import BaseResult, Block, PageLayout, TextSpan
from docmirror.runtime.optional_deps import require_optional_module
from docmirror.tables.classifier import get_last_layer_timings

from .entity_collector import collect_kv_entities
from .foundation import FitzEngine
from .image_converter import image_to_virtual_pdf
from .page_splitter import (
    DocumentSpreadPlan,
    LogicalPageSlice,
    PageSplitDecision,
    analyze_spread_candidates,
    build_document_plan,
    split_or_passthrough,
)
from .scanned_table_reconstructor import reconstruct_scanned_statement_table
from .table_postprocessor import process_page_tables

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _OcrLogicalPage:
    page_number: int
    source_page_number: int
    width: float
    height: float
    blocks: tuple[Block, ...]
    coordinate_transform: dict[str, Any]
    image: Any | None = None


def _selected_page_indices(plane: Any, parse_control: Any) -> set[int]:
    total = len(getattr(plane, "pages", []) or [])
    if total <= 0:
        return set()
    pages_control = getattr(parse_control, "pages", None) if parse_control is not None else None
    if pages_control is None:
        return set(range(total))
    selected = pages_control.resolve(total)
    return set(selected or range(total))


def _should_ocr_page(ocr_mode: str, page_atoms: list[Any]) -> bool:
    if ocr_mode == "off":
        return False
    if ocr_mode == "force":
        return True
    return not page_atoms


def _ocr_blocks_for_pdf_page(
    file_path: Path,
    page_index: int,
    page_number: int,
    *,
    start_order: int = 0,
) -> tuple[list[Block], Any | None]:
    import fitz

    from docmirror.ocr.vision.rapidocr_engine import get_ocr_engine

    np = require_optional_module("numpy", feature="PDF page OCR fallback", extra="ocr")
    zoom = 2.0
    with fitz.open(file_path) as doc:
        if page_index < 0 or page_index >= len(doc):
            return [], None
        page = doc[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n >= 3:
        image = image[:, :, :3]

    words, rotation, selected_image, page_width, page_height, ocr_metrics = _select_ocr_orientation(
        image, get_ocr_engine(), zoom=zoom
    )
    blocks: list[Block] = []
    for index, word in enumerate(words):
        if len(word) < 5:
            continue
        x0, y0, x1, y1, text = word[:5]
        confidence = float(word[8]) if len(word) > 8 else 1.0
        text = str(text or "").strip()
        if not text:
            continue
        bbox = (float(x0) / zoom, float(y0) / zoom, float(x1) / zoom, float(y1) / zoom)
        block_id = f"ocr:p{page_number:04d}:{index:04d}"
        blocks.append(
            Block(
                block_id=block_id,
                block_type="text",
                spans=(TextSpan(text=text, bbox=bbox),),
                bbox=bbox,
                reading_order=start_order + index,
                page=page_number,
                raw_content=text,
                attrs={
                    "ocr_source": "rapidocr_pdf_page",
                    "confidence": round(confidence, 4),
                    "ocr_rotation": rotation,
                    "ocr_orientation_score": ocr_metrics["score"],
                    "normalized_page_width": page_width,
                    "normalized_page_height": page_height,
                },
                evidence_ids=(block_id,),
            )
        )
    return blocks, selected_image


def _select_ocr_orientation(
    image: Any,
    engine: Any,
    *,
    zoom: float,
    forced_rotations: tuple[int, ...] = (),
    probe_low_quality: bool = True,
) -> tuple[list[Any], int, Any, float, float, dict[str, Any]]:
    candidates: list[tuple[float, int, list[Any], Any, dict[str, Any]]] = []
    original_words = engine.detect_image_words(image)
    original_metrics = _ocr_orientation_metrics(original_words)
    candidates.append((float(original_metrics["score"]), 0, original_words, image, original_metrics))
    rotations = set(forced_rotations)
    if probe_low_quality and _needs_orientation_probe(original_metrics):
        rotations.update((90, 180, 270))
    for rotation in (90, 180, 270):
        if rotation in rotations:
            rotated = _rotate_image(image, rotation)
            words = engine.detect_image_words(rotated)
            metrics = _ocr_orientation_metrics(words)
            candidates.append((float(metrics["score"]), rotation, words, rotated, metrics))
    _score, rotation, words, selected_image, metrics = max(candidates, key=lambda item: item[0])
    return (
        words,
        rotation,
        selected_image,
        round(float(selected_image.shape[1]) / zoom, 4),
        round(float(selected_image.shape[0]) / zoom, 4),
        metrics,
    )


def _needs_orientation_probe(metrics: dict[str, Any]) -> bool:
    if float(metrics["score"]) < 260:
        return True
    if int(metrics["keywords"]) == 0 and int(metrics["long_cjk"]) < 8 and int(metrics["garbage_zero9"]) >= 3:
        return True
    return False


def _rotate_image(image: Any, rotation: int) -> Any:
    import cv2

    if rotation == 0:
        return image
    if rotation == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if rotation == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    if rotation == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    raise ValueError(f"unsupported OCR rotation: {rotation}")


def _ocr_orientation_metrics(words: list[Any]) -> dict[str, Any]:
    import re

    keywords = (
        "个人信用报告",
        "报告编号",
        "查询请求时间",
        "身份信息",
        "信贷交易信息",
        "资产负债表",
        "利润表",
        "现金流量表",
        "所有者权益变动表",
        "合并所有者权益变动表",
        "本年发生额",
        "上年发生额",
        "所有者权益合计",
        "实收资本",
        "资本公积",
        "未分配利润",
    )
    texts = [str(word[4] or "").strip() for word in words if len(word) >= 5 and str(word[4] or "").strip()]
    joined = " ".join(texts)
    early_joined = " ".join(texts[:20])
    keyword_hits = sum(joined.count(keyword) for keyword in keywords)
    early_keyword_hits = sum(early_joined.count(keyword) for keyword in keywords)
    number_count = sum(1 for text in texts if re.search(r"\d[\d,]*(?:\.\d+)?", text))
    cjk_count = sum(1 for text in texts if re.search(r"[\u4e00-\u9fff]", text))
    long_cjk = sum(1 for text in texts if len(re.findall(r"[\u4e00-\u9fff]", text)) >= 2)
    garbage_zero9 = sum(1 for text in texts if re.fullmatch(r"[0Oo9]{3,}", text))
    score = (
        len(joined)
        + keyword_hits * 60
        + early_keyword_hits * 90
        + long_cjk * 6
        + number_count * 2
        + cjk_count
        - garbage_zero9 * 20
    )
    return {
        "score": round(float(score), 4),
        "word_count": len(texts),
        "char_count": len(joined),
        "keywords": keyword_hits,
        "early_keywords": early_keyword_hits,
        "numbers": number_count,
        "cjk_tokens": cjk_count,
        "long_cjk": long_cjk,
        "garbage_zero9": garbage_zero9,
    }


def _build_pdf_spread_plan(
    file_path: Path,
    plane: Any,
    *,
    mode: str,
) -> DocumentSpreadPlan:
    """Render cheap thumbnails and build stable physical-to-logical numbering."""
    source_page_numbers = [int(page.page_number) for page in getattr(plane, "pages", []) or []]
    if mode == "off" or file_path.suffix.lower() != ".pdf":
        return build_document_plan({}, source_page_numbers=source_page_numbers, mode="off")

    page_has_text = {
        page.page_id: any(
            atom.page_id == page.page_id and str(atom.text or "").strip()
            for atom in getattr(getattr(plane, "evidence", None), "text_atoms", []) or []
        )
        for page in getattr(plane, "pages", []) or []
    }
    analyses_by_page: dict[int, tuple[Any, ...]] = {}
    try:
        import fitz

        np = require_optional_module("numpy", feature="PDF spread-page analysis", extra="ocr")
        with fitz.open(file_path) as doc:
            for page in getattr(plane, "pages", []) or []:
                if page_has_text.get(page.page_id):
                    continue
                if page.page_index < 0 or page.page_index >= len(doc):
                    continue
                pix = doc[page.page_index].get_pixmap(matrix=fitz.Matrix(0.75, 0.75), alpha=False)
                image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                if pix.n >= 3:
                    image = image[:, :, :3]
                analyses_by_page[int(page.page_number)] = analyze_spread_candidates(image)
    except Exception as exc:
        logger.debug("[DocMirror] spread-page pre-analysis skipped: %s", exc)
        analyses_by_page = {}
    return build_document_plan(
        analyses_by_page,
        source_page_numbers=source_page_numbers,
        mode=mode if mode in {"auto", "off", "force"} else "auto",
    )


def _probe_document_ocr_rotation(file_path: Path, spread_plan: DocumentSpreadPlan) -> int | None:
    """Resolve the shared upright rotation once on a cheap thumbnail."""
    candidates = [
        (source_page_number, decision)
        for source_page_number, decision in spread_plan.decisions.items()
        if decision.should_split and decision.rotation_candidates
    ]
    if not candidates:
        return None
    source_page_number, decision = candidates[0]
    try:
        import fitz

        from docmirror.ocr.vision.rapidocr_engine import get_ocr_engine

        np = require_optional_module("numpy", feature="PDF spread orientation probe", extra="ocr")
        zoom = 0.75
        with fitz.open(file_path) as doc:
            if source_page_number <= 0 or source_page_number > len(doc):
                return None
            pix = doc[source_page_number - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n >= 3:
            image = image[:, :, :3]
        _words, rotation, _selected, _width, _height, _metrics = _select_ocr_orientation(
            image,
            get_ocr_engine(),
            zoom=zoom,
            forced_rotations=decision.rotation_candidates,
            probe_low_quality=False,
        )
        return rotation
    except Exception as exc:
        logger.debug("[DocMirror] document spread orientation probe skipped: %s", exc)
        return None


def _ocr_logical_pages_for_pdf_page(
    file_path: Path,
    page_index: int,
    source_page_number: int,
    *,
    logical_start: int,
    source_width: float,
    source_height: float,
    decision: PageSplitDecision,
    page_split_mode: str,
    preferred_rotation: int | None = None,
) -> list[_OcrLogicalPage]:
    """OCR one physical page and return one or more logical page results."""
    if not decision.should_split:
        ocr_result = _ocr_blocks_for_pdf_page(file_path, page_index, source_page_number)
        if isinstance(ocr_result, tuple) and len(ocr_result) == 2:
            blocks, selected_image = ocr_result
        else:  # Backward-compatible test/extension seam.
            blocks, selected_image = ocr_result, None
        rotation = 0
        width, height = source_width, source_height
        for block in blocks:
            attrs = block.attrs or {}
            rotation = int(attrs.get("ocr_rotation") or 0) % 360
            width = float(attrs.get("normalized_page_width") or width)
            height = float(attrs.get("normalized_page_height") or height)
            break
        matrix = rotation_matrix(source_width, source_height, rotation)
        transform = _logical_page_transform(
            source_page_number=source_page_number,
            matrix=matrix,
            inverse_matrix=invert_matrix(matrix),
            source_crop_bbox=(0.0, 0.0, source_width, source_height),
            rotation=rotation,
            split_kind="none",
            segment_index=0,
            confidence=decision.confidence,
            width=width,
            height=height,
        )
        repaged = _repage_blocks(blocks, logical_start, source_page_number)
        return [
            _OcrLogicalPage(
                page_number=logical_start,
                source_page_number=source_page_number,
                width=width,
                height=height,
                blocks=tuple(repaged),
                coordinate_transform=transform,
                image=selected_image,
            )
        ]

    import fitz

    from docmirror.ocr.vision.rapidocr_engine import get_ocr_engine

    np = require_optional_module("numpy", feature="PDF spread-page OCR", extra="ocr")
    zoom = 2.0
    with fitz.open(file_path) as doc:
        if page_index < 0 or page_index >= len(doc):
            return []
        page = doc[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n >= 3:
        image = image[:, :, :3]

    engine = get_ocr_engine()
    if preferred_rotation is not None and preferred_rotation in decision.rotation_candidates:
        rotation = int(preferred_rotation) % 360
        selected_image = _rotate_image(image, rotation)
        full_words: list[Any] = []
        full_metrics: dict[str, Any] = {"score": 0.0}
        _page_width = round(float(selected_image.shape[1]) / zoom, 4)
        _page_height = round(float(selected_image.shape[0]) / zoom, 4)
    else:
        full_words, rotation, selected_image, _page_width, _page_height, full_metrics = _select_ocr_orientation(
            image,
            engine,
            zoom=zoom,
            forced_rotations=decision.rotation_candidates,
        )
    slices = split_or_passthrough(
        selected_image,
        source_width=source_width,
        source_height=source_height,
        selected_rotation=rotation,
        zoom=zoom,
        decision=decision,
        mode=page_split_mode if page_split_mode in {"auto", "off", "force"} else "auto",
    )
    out: list[_OcrLogicalPage] = []
    for offset, page_slice in enumerate(slices):
        logical_page_number = logical_start + offset
        is_full_page = bool(full_words) and (
            len(slices) == 1
            and page_slice.crop_bbox_oriented[0] == 0.0
            and page_slice.crop_bbox_oriented[1] == 0.0
            and abs(page_slice.width - _page_width) < 1.0
            and abs(page_slice.height - _page_height) < 1.0
        )
        words = full_words if is_full_page else engine.detect_image_words(page_slice.image)
        metrics = full_metrics if is_full_page else _ocr_orientation_metrics(words)
        blocks = _ocr_words_to_blocks(
            words,
            logical_page_number=logical_page_number,
            source_page_number=source_page_number,
            rotation=rotation,
            zoom=zoom,
            page_width=page_slice.width,
            page_height=page_slice.height,
            metrics=metrics,
        )
        transform = _logical_page_transform_from_slice(
            page_slice,
            source_page_number=source_page_number,
            width=page_slice.width,
            height=page_slice.height,
        )
        out.append(
            _OcrLogicalPage(
                page_number=logical_page_number,
                source_page_number=source_page_number,
                width=page_slice.width,
                height=page_slice.height,
                blocks=tuple(blocks),
                coordinate_transform=transform,
                image=page_slice.image,
            )
        )
    return out


def _ocr_words_to_blocks(
    words: list[Any],
    *,
    logical_page_number: int,
    source_page_number: int,
    rotation: int,
    zoom: float,
    page_width: float,
    page_height: float,
    metrics: dict[str, Any],
) -> list[Block]:
    blocks: list[Block] = []
    for index, word in enumerate(words):
        if len(word) < 5:
            continue
        x0, y0, x1, y1, text = word[:5]
        confidence = float(word[8]) if len(word) > 8 else 1.0
        text = str(text or "").strip()
        if not text:
            continue
        bbox = (float(x0) / zoom, float(y0) / zoom, float(x1) / zoom, float(y1) / zoom)
        block_id = f"ocr:sp{source_page_number:04d}:lp{logical_page_number:04d}:{index:04d}"
        blocks.append(
            Block(
                block_id=block_id,
                block_type="text",
                spans=(TextSpan(text=text, bbox=bbox),),
                bbox=bbox,
                reading_order=index,
                page=logical_page_number,
                raw_content=text,
                attrs={
                    "ocr_source": "rapidocr_pdf_logical_page",
                    "confidence": round(confidence, 4),
                    "ocr_rotation": rotation,
                    "ocr_orientation_score": metrics["score"],
                    "normalized_page_width": page_width,
                    "normalized_page_height": page_height,
                    "source_page_number": source_page_number,
                    "logical_page_number": logical_page_number,
                },
                evidence_ids=(block_id,),
            )
        )
    return blocks


def _repage_blocks(blocks: list[Block], logical_page_number: int, source_page_number: int) -> list[Block]:
    return [
        replace(
            block,
            page=logical_page_number,
            attrs={
                **dict(block.attrs or {}),
                "source_page_number": source_page_number,
                "logical_page_number": logical_page_number,
            },
        )
        for block in blocks
    ]


def _logical_page_transform_from_slice(
    page_slice: LogicalPageSlice,
    *,
    source_page_number: int,
    width: float,
    height: float,
) -> dict[str, Any]:
    return _logical_page_transform(
        source_page_number=source_page_number,
        matrix=page_slice.source_to_logical,
        inverse_matrix=page_slice.logical_to_source,
        source_crop_bbox=page_slice.source_crop_bbox,
        rotation=page_slice.selected_rotation,
        split_kind="two_page_spread",
        segment_index=page_slice.segment_index,
        confidence=page_slice.split_confidence,
        width=width,
        height=height,
    )


def _logical_page_transform(
    *,
    source_page_number: int,
    matrix: list[list[float]],
    inverse_matrix: list[list[float]],
    source_crop_bbox: tuple[float, float, float, float],
    rotation: int,
    split_kind: str,
    segment_index: int,
    confidence: float,
    width: float,
    height: float,
) -> dict[str, Any]:
    return {
        "source_page_number": source_page_number,
        "source_page_id": f"source-page:{source_page_number:04d}",
        "source_crop_bbox": [round(value, 4) for value in source_crop_bbox],
        "source_rotation": 0,
        "normalized_rotation": 0,
        "content_rotation_applied": int(rotation) % 360,
        "matrix": matrix,
        "inverse_matrix": inverse_matrix,
        "source_width": float(source_crop_bbox[2] - source_crop_bbox[0]),
        "source_height": float(source_crop_bbox[3] - source_crop_bbox[1]),
        "display_width": width,
        "display_height": height,
        "decomposition": {
            "kind": split_kind,
            "segment_index": segment_index,
            "selected_rotation": int(rotation) % 360,
            "confidence": round(float(confidence), 4),
        },
    }


def _page_layout_from_blocks(
    blocks: list[Block],
    *,
    logical_page_number: int,
    source_page_number: int,
    width: float,
    height: float,
    is_scanned: bool,
    coordinate_transform: dict[str, Any],
    page_image: Any | None = None,
) -> PageLayout:
    from .scanned_table_reconstructor import reconstruct_scanned_bordered_tables

    scanned_tables = reconstruct_scanned_bordered_tables(
        page_image,
        blocks,
        page_number=logical_page_number,
        page_width=width,
        page_height=height,
        start_order=len(blocks),
    )
    if scanned_tables:
        for scanned_table in scanned_tables:
            blocks = _remove_table_owned_text_blocks(blocks, scanned_table)
        blocks.extend(scanned_tables)
    else:
        scanned_table = reconstruct_scanned_statement_table(
            blocks,
            page_number=logical_page_number,
            page_width=width,
            page_height=height,
            start_order=len(blocks),
        )
        if scanned_table is not None:
            blocks = _remove_table_owned_text_blocks(blocks, scanned_table)
            blocks.append(scanned_table)
    return PageLayout(
        page_number=logical_page_number,
        width=width,
        height=height,
        blocks=tuple(blocks),
        is_scanned=is_scanned,
        source_page_number=source_page_number,
        coordinate_transform=dict(coordinate_transform),
    )


def _block_evidence_id_set(block: Block) -> set[str]:
    ids = set(block.evidence_ids or ())
    if not ids and block.block_id:
        ids.add(block.block_id)
    return ids


def _remove_table_owned_text_blocks(blocks: list[Block], table: Block) -> list[Block]:
    owned = set(table.evidence_ids or ())
    if not owned:
        return blocks
    return [block for block in blocks if block.block_type != "text" or not (_block_evidence_id_set(block) & owned)]


def _block_full_text(block: Block) -> str:
    span_text = "\n".join(span.text for span in block.spans if str(span.text or "").strip())
    if span_text:
        return span_text
    if block.block_type == "table" and isinstance(block.raw_content, list):
        return "\n".join(
            "\t".join(str(cell or "") for cell in row) for row in block.raw_content if isinstance(row, list)
        )
    if isinstance(block.raw_content, str):
        return block.raw_content
    return ""


class CoreExtractor:
    """
    Core extractor — generates immutable BaseResult from PDF.

    Usage::

        extractor = CoreExtractor()
        result = await extractor.extract(Path("sample.pdf"))
        # result is frozen BaseResult, immutable

    All low-level functions come from MultiModal.core submodules (self-contained).
    """

    def __init__(
        self,
        seal_detector_fn=None,
        layout_model_path: str | None = None,
        max_page_concurrency: int | None = None,
        formula_model_path: str | None = None,
        model_render_dpi: int = 200,
    ):
        """
        Args:
            seal_detector_fn: Optional seal detection callback function.
                Signature: (fitz_doc) -> Optional[Dict[str, Any]]
                When None, skips seal detection.
            layout_model_path: Optional DocLayout-YOLO ONNX model path.
                Set to "auto" to auto-download from HuggingFace.
                When None, uses rule-based fallback.
            max_page_concurrency: Page-level concurrency.
                pdfplumber/PyMuPDF shared doc object, current default is 1 (sequential).
                Set >1 to use ThreadPoolExecutor for parallel extraction.
            formula_model_path: Optional formula recognition ONNX model path (UniMERNet).
                When None, falls back to rapid_latex_ocr -> empty string.
            model_render_dpi: Page rendering DPI for DocLayout-YOLO model inference.
                Default 200; higher values improve layout detection precision but increase inference time.
        """
        from docmirror.configs.runtime.performance import resolve_max_page_concurrency

        self._seal_detector_fn = seal_detector_fn
        self._layout_detector = None
        self._max_page_concurrency = resolve_max_page_concurrency(max_page_concurrency)
        self._model_render_dpi = model_render_dpi

        # Formula recognition engine (Strategy pattern: UniMERNet ONNX > rapid_latex_ocr > empty)
        from docmirror.ocr.formula_engine import FormulaEngine

        self._formula_engine = FormulaEngine(model_path=formula_model_path)

        if layout_model_path:
            try:
                from docmirror.layout.segment.layout_model import LayoutDetector

                # layout_model_path acts as model type name
                # "auto" -> default doclayout_docstructbench
                model_type = "doclayout_docstructbench" if layout_model_path == "auto" else layout_model_path
                self._layout_detector = LayoutDetector(model_type=model_type)
                logger.info("[DocMirror] Layout model enabled (RapidLayout)")
            except Exception as e:
                logger.warning(f"[DocMirror] Layout model init failed, falling back to rules: {e}")

    # Supported image formats
    _IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"})

    @staticmethod
    def _image_to_virtual_pdf(image_path: Path) -> fitz.Document:
        """Convert image to a virtual single-page PDF, pre-scaling large images to max 4096px."""
        return image_to_virtual_pdf(image_path)

    async def extract(self, file_path: Path, *, options: dict | None = None) -> BaseResult:
        """
        Main entry point: extract BaseResult from PDF or image.

        Extract through the UDTR evidence intake and return a physical BaseResult
        for older adapter boundaries that still expect one.
        """
        file_path = Path(file_path)
        doc_id = str(uuid.uuid4())
        logger.info(f"[DocMirror] ▶ extract | file={file_path.name}")
        try:
            return await self._extract_base_result_vnext(file_path, doc_id=doc_id, options=options or {})
        except ExtractionError as e:
            logger.error(f"[DocMirror] extraction error: {e}", exc_info=True)
            return BaseResult(
                document_id=doc_id,
                metadata={"error": str(e), "error_type": "ExtractionError", "parser": "DocMirror_CoreExtractor"},
                full_text="",
            )
        except Exception as e:
            logger.error(f"[DocMirror] unexpected error: {e}", exc_info=True)
            return BaseResult(
                document_id=doc_id,
                metadata={"error": str(e), "error_type": type(e).__name__, "parser": "DocMirror_CoreExtractor"},
                full_text="",
            )

    async def _extract_base_result_vnext(
        self,
        file_path: Path,
        *,
        doc_id: str,
        options: dict | None = None,
    ) -> BaseResult:
        import asyncio

        from docmirror.evidence.plane import EvidencePlaneBuilder

        started_at = _clock()
        options = dict(options or {})
        parse_control = options.get("parse_control")
        ocr_mode = getattr(getattr(parse_control, "execution", None), "ocr", "auto") if parse_control else "auto"
        plane = await asyncio.to_thread(EvidencePlaneBuilder().build, str(file_path))
        selected_indices = _selected_page_indices(plane, parse_control)
        page_split_mode = (
            getattr(getattr(parse_control, "execution", None), "page_split", "auto") if parse_control else "auto"
        )
        if ocr_mode == "off":
            page_split_mode = "off"
        spread_plan = await asyncio.to_thread(
            _build_pdf_spread_plan,
            file_path,
            plane,
            mode=page_split_mode,
        )
        preferred_spread_rotation = (
            await asyncio.to_thread(_probe_document_ocr_rotation, file_path, spread_plan)
            if page_split_mode != "off"
            else None
        )
        pages: list[PageLayout] = []
        for page in plane.pages:
            if page.page_index not in selected_indices:
                continue
            source_page_number = int(page.page_number)
            logical_start = spread_plan.logical_start_for(source_page_number)
            page_atoms = [
                atom
                for atom in plane.evidence.text_atoms
                if atom.page_id == page.page_id and str(atom.text or "").strip()
            ]
            blocks: list[Block] = []
            for index, atom in enumerate(page_atoms):
                bbox = tuple(float(v) for v in (atom.bbox or [0.0, 0.0, 0.0, 0.0]))
                text = str(atom.text or "")
                blocks.append(
                    Block(
                        block_id=atom.id,
                        block_type="text",
                        spans=(TextSpan(text=text, bbox=bbox),),
                        bbox=bbox,
                        reading_order=index,
                        page=logical_start,
                        raw_content=text,
                        evidence_ids=(atom.id,),
                    )
                )
            if _should_ocr_page(ocr_mode, page_atoms):
                ocr_pages = await asyncio.to_thread(
                    _ocr_logical_pages_for_pdf_page,
                    file_path,
                    page.page_index,
                    source_page_number,
                    logical_start=logical_start,
                    source_width=float(page.width or 0.0),
                    source_height=float(page.height or 0.0),
                    decision=spread_plan.decision_for(source_page_number),
                    page_split_mode=page_split_mode,
                    preferred_rotation=preferred_spread_rotation,
                )
                if ocr_pages:
                    for ocr_page in ocr_pages:
                        page_blocks = list(ocr_page.blocks)
                        if blocks and len(ocr_pages) == 1:
                            page_blocks = blocks + [
                                replace(block, reading_order=len(blocks) + block.reading_order) for block in page_blocks
                            ]
                        pages.append(
                            _page_layout_from_blocks(
                                page_blocks,
                                logical_page_number=ocr_page.page_number,
                                source_page_number=source_page_number,
                                width=ocr_page.width,
                                height=ocr_page.height,
                                is_scanned=True,
                                coordinate_transform=ocr_page.coordinate_transform,
                                page_image=ocr_page.image,
                            )
                        )
                    continue

            identity_matrix = rotation_matrix(float(page.width or 0.0), float(page.height or 0.0), 0)
            transform = _logical_page_transform(
                source_page_number=source_page_number,
                matrix=identity_matrix,
                inverse_matrix=invert_matrix(identity_matrix),
                source_crop_bbox=(0.0, 0.0, float(page.width or 0.0), float(page.height or 0.0)),
                rotation=0,
                split_kind="none",
                segment_index=0,
                confidence=1.0,
                width=float(page.width or 0.0),
                height=float(page.height or 0.0),
            )
            pages.append(
                _page_layout_from_blocks(
                    blocks,
                    logical_page_number=logical_start,
                    source_page_number=source_page_number,
                    width=float(page.width or 0.0),
                    height=float(page.height or 0.0),
                    is_scanned=False,
                    coordinate_transform=transform,
                    page_image=None,
                )
            )
        table_count = sum(1 for page in pages for block in page.blocks if block.block_type == "table")
        confidence_values: list[tuple[float, int]] = []
        for logical_page in pages:
            for block in logical_page.blocks:
                attrs = block.attrs or {}
                raw_confidence = attrs.get("confidence", attrs.get("extraction_confidence"))
                if raw_confidence is None:
                    continue
                try:
                    confidence = max(0.0, min(1.0, float(raw_confidence)))
                except (TypeError, ValueError):
                    continue
                confidence_values.append((confidence, max(1, len(_block_full_text(block)))))
        confidence_weight = sum(weight for _confidence, weight in confidence_values)
        overall_confidence = (
            sum(confidence * weight for confidence, weight in confidence_values) / confidence_weight
            if confidence_weight
            else (0.0 if any(page.is_scanned for page in pages) else 1.0)
        )
        has_scanned = any(page.is_scanned for page in pages)
        has_native = any(not page.is_scanned for page in pages)
        extraction_method = "hybrid" if has_scanned and has_native else ("ocr" if has_scanned else "digital")
        sample_text = "\n".join(
            text for logical_page in pages for block in logical_page.blocks if (text := _block_full_text(block)).strip()
        )
        metadata = {
            "parser": "DocMirror_CoreExtractor",
            "pipeline": "udtr_vnext",
            "elapsed_ms": round((_clock() - started_at) * 1000.0, 3),
            "extraction_method": extraction_method,
            "ocr_engine": "rapidocr_onnxruntime" if has_scanned else None,
            "table_engine": "scanned_image_line_grid" if table_count and has_scanned else "pymupdf_native",
            "overall_confidence": round(overall_confidence, 4),
            "warnings": ["low_ocr_confidence"] if has_scanned and overall_confidence < 0.8 else [],
            "selected_pages": [page.page_number for page in pages],
            "selected_source_pages": [
                int(page.page_number) for page in plane.pages if page.page_index in selected_indices
            ],
            "ocr_mode": ocr_mode,
            "page_split_mode": page_split_mode,
            "page_split_rotation": preferred_spread_rotation,
            "source_page_count": len(plane.pages),
            "logical_page_count": spread_plan.logical_page_count,
            "page_decomposition": {
                "method": "rotated_two_page_spread"
                if any(decision.should_split for decision in spread_plan.decisions.values())
                else "none",
                "confidence": spread_plan.confidence,
            },
        }
        metadata["structure"] = self._build_vnext_structure_metadata(
            sample_text=sample_text,
            table_count=table_count,
            extraction_layer="udtr_vnext",
            physical_table_count=table_count,
        )
        metadata["structure"]["source_page_count"] = len(plane.pages)
        metadata["structure"]["logical_page_count"] = spread_plan.logical_page_count
        return BaseResult(
            document_id=doc_id,
            pages=tuple(pages),
            metadata=metadata,
            full_text="\n".join(
                text for page in pages for block in page.blocks if (text := _block_full_text(block)).strip()
            ),
        )

    @staticmethod
    def _build_vnext_structure_metadata(
        *,
        sample_text: str,
        table_count: int,
        extraction_layer: str,
        physical_table_count: int | None = None,
    ) -> dict[str, Any]:
        from docmirror.evidence.structure_provenance import build_structure_provenance
        from docmirror.layout.structure_signals import score_pipe_grid, score_section_headers

        h_section = score_section_headers(sample_text)
        h_pipe = score_pipe_grid(sample_text)
        if table_count > 0 or h_pipe >= 0.85:
            content_type = "table_dominant"
        elif h_section >= 0.3:
            content_type = "section_dominant"
        elif sample_text.strip():
            content_type = "text_dominant"
        else:
            content_type = "unknown"
        spe = build_structure_provenance(
            content_type=content_type,
            sample_text=sample_text,
            table_count=table_count,
            extraction_layer=extraction_layer,
            competitors={"H_section": h_section, "H_pipe_grid": h_pipe},
        ).to_dict()
        spe["physical_table_count"] = physical_table_count
        return spe

    async def extract_parse_result(self, file_path: Path, *, options: dict | None = None) -> ParseResult:
        """
        Single bridge point: CoreExtractor → ParseResult (MOC Path B).

        Prefer this over ``extract()`` + manual ``ParseResultBridge.from_base_result()``
        in adapters (design 09 §5 Phase 1).
        """
        from docmirror.input.bridge.parse_result_bridge import ParseResultBridge

        base_result = await self.extract(file_path, options=options or {})
        return ParseResultBridge.from_base_result(base_result)

    async def _open_document(self, file_path: Path) -> fitz.Document:
        """Open a document (PDF or image). Returns the PyMuPDF document."""
        import asyncio

        is_image = file_path.suffix.lower() in self._IMAGE_SUFFIXES
        if is_image:
            fitz_doc = await asyncio.to_thread(self._image_to_virtual_pdf, file_path)
            logger.info("[DocMirror] Image input -> virtual PDF, marked as scanned document")
            return fitz_doc

        cleaned_path = await asyncio.to_thread(preprocess_document, file_path)
        fitz_doc = await asyncio.to_thread(FitzEngine.open, cleaned_path)
        has_text = await asyncio.to_thread(FitzEngine.has_text_layer, fitz_doc)
        if not has_text:
            logger.info("[DocMirror] Text layer missing, marked as scanned document")
        return fitz_doc

    async def _run_extraction(
        self, fitz_doc: fitz.Document, file_path: Path, doc_id: str, options: dict | None = None
    ) -> BaseResult:
        """Core extraction logic, extracted from try block.

        Steps:
          1. Pre-analysis
          2. CPU-bound parsing (in thread)
          3. QGE quality gate / direct path for low-quality images
          4. Assemble BaseResult
        """
        import asyncio

        t0 = _clock()
        options = dict(options or {})
        _on_progress = options.get("on_progress")
        if _on_progress:
            _on_progress("load_document", 1.0, "Analyzing document structure...")
        file_path = Path(file_path)
        is_image_input = file_path.suffix.lower() in self._IMAGE_SUFFIXES
        self._page_evidence_bundles = []

        # Step 1.5: Pre-analysis (UDTR replacement — simple defaults)
        class _DefaultPreAnalysis:
            content_type = "text_dominant"
            quality_score = 1.0
            scene_hint = ""
            content_language = ""
            homogeneous = True
            complexity = "simple"
            strategy = "fast"
            n_pages = 0

        pre_analysis = _DefaultPreAnalysis()
        _pa_quality = 1.0

        # Optimization: skip heavy scanned-page restoration for low-quality images.
        # The scanned restoration path is designed for high-quality scanner output;
        # phone photos / screenshots with quality < 0.5 nearly always
        # produce garbage there. Go directly to plain-OCR QGE path.
        if is_image_input and _pa_quality < 0.5:
            logger.info(
                f"[QGE] Low-quality image (quality={_pa_quality:.2f}), skipping scanned pipeline, running direct OCR"
            )
            ocr_blocks, qge_tokens = CoreExtractor._qge_plain_ocr_fallback(file_path)
            if ocr_blocks:
                pages, full_text = CoreExtractor._qge_build_pages_from_blocks(ocr_blocks)
            else:
                pages, full_text = [], ""
            if qge_tokens:
                self._page_evidence_bundles.append(
                    {
                        "page": 1,
                        "tokens": qge_tokens,
                        "source": "qge_fallback",
                    }
                )
            extraction_layer = "ocr"
            extraction_confidence = 0.8
            _perf = {
                "page_count": len(pages),
                "source_page_count": len(pages),
                "document_scene": "unknown",
                "scene_confidence": 0.0,
                "layout_profile_id": None,
                "selected_pages": [p.page_number for p in pages],
                "scanned_pages": [],
                "has_text_layer": False,
                "dual_view": False,
                "pipe_table_enrich": False,
            }
            _page_perf = []
        else:
            # Step 2-5: CPU-bound parsing (layout, page extraction, tables, post-processing)
            if _on_progress:
                _on_progress("page_extraction", 0.0, "Extracting page layouts & tables...")
            pages, full_text, extraction_layer, extraction_confidence, _perf, _page_perf = await asyncio.to_thread(
                self._process_pdf_sync,
                fitz_doc=fitz_doc,
                pre_analysis=pre_analysis,
                has_text=fitz_doc is not None,
                is_image_input=is_image_input,
                cleaned_path=None,
                file_path=file_path,
                options=options,
            )

            # ── QGE: Quality-Gated Extraction (image-only plain OCR fallback) ──
            if is_image_input and pages:
                quality = CoreExtractor._qge_assess_quality(pages, full_text)
                if quality.score < 0.3:
                    logger.warning(
                        f"[QGE] Extraction quality low (score={quality.score:.2f}, "
                        f"reason={quality.reason}), running plain OCR fallback"
                    )
                    ocr_blocks, qge_tokens = CoreExtractor._qge_plain_ocr_fallback(file_path)
                    if ocr_blocks:
                        pages, full_text, _, _ = CoreExtractor._qge_merge_results(pages, full_text, ocr_blocks)
                    if qge_tokens:
                        self._page_evidence_bundles.append(
                            {
                                "page": 1,
                                "tokens": qge_tokens,
                                "source": "qge_fallback",
                            }
                        )

        # Step 6: Assemble BaseResult
        elapsed = (_clock() - t0) * 1000
        total_blocks = sum(len(p.blocks) for p in pages)
        table_count = sum(1 for p in pages for b in p.blocks if b.block_type == "table")
        extracted_entities = self._collect_kv_entities(pages)

        # Seal detection (optional, DI)
        seal_info = None
        if self._seal_detector_fn:
            try:
                seal_info = self._seal_detector_fn(fitz_doc)
            except Exception as e:
                logger.debug(f"[DocMirror] Seal detection skip: {e}")

        # Extract logical tables from _perf before it's nested
        _logical_tables_data = _perf.pop("_logical_tables", None) if isinstance(_perf, dict) else None

        metadata: dict[str, Any] = {
            "file_name": file_path.name,
            "file_size": file_path.stat().st_size,  # L2 guarantees file exists
            "page_count": len(pages),
            "source_page_count": _perf.get("source_page_count"),
            "processed_page_numbers": _perf.get("selected_pages") or [p.page_number for p in pages],
            "document_scene": getattr(self, "_document_scene", None) or _perf.get("document_scene", "unknown"),
            "scene_confidence": getattr(self, "_scene_confidence", 0.0) or _perf.get("scene_confidence", 0.0),
            "layout_profile_id": _perf.get("layout_profile_id"),
            "quarantined_tables": _perf.get("quarantined_tables") or [],
            "parser": "DocMirror_CoreExtractor",
            "elapsed_ms": round(elapsed, 1),
            "block_count": total_blocks,
            "table_count": table_count,
            "has_text_layer": fitz_doc is not None,
            "scanned_pages": [p.page_number for p in pages if p.is_scanned],
            "pre_analysis": pre_analysis.to_dict(),
            "extracted_entities": extracted_entities,
            "perf_breakdown": _perf,
            "perf_per_page": _page_perf,
        }
        opts = dict(options or {})
        parse_control = opts.get("parse_control")
        parse_control_dict = opts.get("parse_control_dict")
        if parse_control_dict is None and parse_control is not None and hasattr(parse_control, "to_dict"):
            parse_control_dict = parse_control.to_dict()
        if parse_control_dict:
            metadata["parse_control"] = parse_control_dict
            metadata["parse_control_fingerprint"] = opts.get("parse_control_fingerprint") or (
                parse_control.fingerprint()
                if parse_control is not None and hasattr(parse_control, "fingerprint")
                else ""
            )
            pages_control = parse_control_dict.get("pages") if isinstance(parse_control_dict, dict) else {}
            if isinstance(pages_control, dict):
                metadata["selected_pages"] = pages_control
        if opts.get("doc_type_hint"):
            metadata["doc_type_hint"] = opts.get("doc_type_hint")
            metadata["doc_type_hint_strength"] = opts.get("doc_type_hint_strength") or "prefer"
        stage_timings = getattr(self, "_page_stage_timings", None)
        if stage_timings:
            metadata["perf_stage_timings"] = stage_timings

        # Pass logical tables to bridge layer via metadata
        if _logical_tables_data:
            metadata["_logical_tables"] = _logical_tables_data

        ltqg_summary = getattr(self, "_ltqg_summary", None)
        if ltqg_summary:
            metadata["ltqg"] = ltqg_summary

        quarantined_logical = getattr(self, "_quarantined_logical_tables", None)
        if quarantined_logical:
            metadata["quarantined_logical_tables"] = quarantined_logical

        section_tree = _perf.pop("_section_tree", None)
        if section_tree:
            metadata["sections"] = section_tree
        if seal_info:
            metadata["seal_info"] = seal_info
        page_evidence_bundles = getattr(self, "_page_evidence_bundles", None)
        if page_evidence_bundles:
            metadata["page_evidence_bundles"] = list(page_evidence_bundles)

        if table_count > 0:
            metadata["extraction_quality"] = self._assess_extraction_quality(
                pages, extraction_layer, extraction_confidence
            )

        metadata["structure"] = self._build_structure_metadata(
            pre_analysis=pre_analysis,
            fitz_doc=fitz_doc,
            table_count=table_count,
            extraction_layer=extraction_layer,
            layout_profile_id=_perf.get("layout_profile_id"),
            pipe_table_enrich=bool(_perf.get("pipe_table_enrich")),
            logical_table_count=len(_logical_tables_data) if _logical_tables_data else None,
            physical_table_count=table_count,
            dual_view=_perf.get("dual_view") if isinstance(_perf, dict) else None,
            ltqg_summary=_perf.get("ltqg") if isinstance(_perf, dict) else None,
        )

        result = BaseResult(
            document_id=doc_id,
            pages=tuple(pages),
            metadata=metadata,
            full_text=full_text,
        )

        logger.info(
            f"[DocMirror] ◀ extract | pages={len(pages)} | blocks={total_blocks} | "
            f"tables={table_count} | elapsed={elapsed:.0f}ms"
        )
        return result

    @staticmethod
    def _build_structure_metadata(
        *,
        pre_analysis,
        fitz_doc,
        table_count: int,
        extraction_layer: str,
        layout_profile_id: str | None,
        pipe_table_enrich: bool = False,
        logical_table_count: int | None = None,
        physical_table_count: int | None = None,
        dual_view: bool | None = None,
        ltqg_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build SPE dict for parser_info.structure (ADR-M13-02)."""
        from docmirror.evidence.structure_provenance import (
            apply_logical_tables_spe,
            apply_pipe_enrich_spe,
            build_structure_provenance,
        )
        from docmirror.layout.structure_signals import build_sso_sample_text

        sample_text = build_sso_sample_text(fitz_doc) if fitz_doc is not None else ""

        def _with_logical_tables(spe_dict: dict[str, Any]) -> dict[str, Any]:
            return apply_logical_tables_spe(
                spe_dict,
                logical_table_count=logical_table_count,
                physical_table_count=physical_table_count,
                dual_view=dual_view,
                ltqg_summary=ltqg_summary,
            )

        structural = getattr(pre_analysis, "structure_spe", None)
        if structural:
            out = dict(structural)
            out["extraction_layer"] = extraction_layer
            out["layout_profile_id"] = layout_profile_id
            if pipe_table_enrich:
                return _with_logical_tables(apply_pipe_enrich_spe(out))
            if table_count > 0:
                out["table_extraction"] = "full"
                out["table_extraction_skipped_reason"] = None
            elif out.get("table_extraction") == "full" and table_count == 0:
                out["table_extraction_skipped_reason"] = (
                    out.get("table_extraction_skipped_reason") or "extraction_failed"
                )
            return _with_logical_tables(out)

        spe = build_structure_provenance(
            content_type=getattr(pre_analysis, "content_type", "unknown"),
            sample_text=sample_text,
            table_count=table_count,
            extraction_layer=extraction_layer,
            layout_profile_id=layout_profile_id,
            table_extraction="enrich_only" if pipe_table_enrich else None,
        )
        if pipe_table_enrich:
            return _with_logical_tables(apply_pipe_enrich_spe(spe.to_dict()))
        return _with_logical_tables(spe.to_dict())

    # ─────────────────────────────────────────────────────────────────────────────
    # QGE: Quality-Gated Extraction (plain OCR fallback for image inputs)
    # ─────────────────────────────────────────────────────────────────────────────
    # When the primary pipeline extracts very little text from an image input
    # (e.g. photographed screenshot, unusual layout), this fallback runs RapidOCR
    # directly (bypassing layout analysis) and merges the resulting text blocks
    # into the output.  This ensures the user always gets *some* searchable text
    # even when the layout/table pipeline fails.

    class _QgeQuality:
        """Quality assessment result — score < 0.3 triggers fallback."""

        __slots__ = ("score", "total_blocks", "total_text_chars", "table_count", "reason")

        def __init__(
            self, score: float, total_blocks: int, total_text_chars: int, table_count: int, reason: str | None = None
        ):
            self.score = score
            self.total_blocks = total_blocks
            self.total_text_chars = total_text_chars
            self.table_count = table_count
            self.reason = reason

    @staticmethod
    def _preprocess_ocr_image(img):
        import cv2

        np = require_optional_module("numpy", feature="OCR image preprocessing", extra="ocr")
        if img is None:
            return img
        if img.size == 0 or img.shape[0] < 10 or img.shape[1] < 10:
            return img
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        if lap_var >= 200:
            return img
        h, w = gray.shape[:2]
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, max(50, int(min(w, h) * 0.06)))
        if lines is not None:
            mean_angle = np.mean([[line[0][1] for line in lines[:10]]])
            angle_deg = (mean_angle * 180 / np.pi) - 90
            if abs(angle_deg) > 0.5 and abs(angle_deg) < 45:
                center = (w // 2, h // 2)
                rot = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
                gray = cv2.warpAffine(gray, rot, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        h, w = gray.shape[:2]
        if max(w, h) < 1200:
            gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        blur = cv2.GaussianBlur(gray, (0, 0), 1.5)
        gray = cv2.addWeighted(gray, 1.5, blur, -0.5, 0)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR) if len(img.shape) == 3 else gray

    @staticmethod
    def _qge_assess_quality(pages: list, full_text: str) -> _QgeQuality:
        """Assess extraction quality: text density + structural coverage.

        Three signals:
          - text_density:  chars / 500 (capped at 1.0)
          - blob_penalty:  if avg chars/block > 300, text is likely a
                           concatenated blob from the scanned pipeline
          - structure:     blocks/5 * 0.5 + tables/1 * 0.5 (capped at 1.0)

        Score = text_coverage * 0.5 + structural_coverage * 0.5
        """
        total_blocks = 0
        total_text_chars = len(full_text) if full_text else 0
        table_count = 0
        for p in pages:
            for b in p.blocks:
                total_blocks += 1
                if b.block_type == "table":
                    table_count += 1

        text_score = min(1.0, total_text_chars / 500)

        # Blob penalty: text crammed into few blocks → suspicious
        avg_chars_per_block = total_text_chars / max(1, total_blocks)
        if avg_chars_per_block > 300:
            blob_penalty = max(0.2, 1.0 - (avg_chars_per_block - 300) / 700)
            text_score *= blob_penalty

        structure_score = min(1.0, (total_blocks / 5) * 0.5 + (table_count / 1) * 0.5)
        score = text_score * 0.5 + structure_score * 0.5

        if table_count > 0:
            reason = None
        elif total_text_chars < 100:
            reason = "text_too_sparse"
        elif total_blocks < 3 and text_score < 0.5:
            reason = "no_structure"
        elif avg_chars_per_block > 300 and total_blocks < 5:
            reason = "text_blob"
        else:
            reason = None

        return CoreExtractor._QgeQuality(score, total_blocks, total_text_chars, table_count, reason)

    @staticmethod
    def _qge_plain_ocr_fallback(file_path: Path) -> tuple[list[Block], list[dict]]:
        """Bypass layout analysis; run RapidOCR detect_image_words directly.

        Returns a list of ``Block`` (type=text) with position and confidence,
        or empty list if OCR fails.

        This is the same code path as ``ImageAdapter._extract_text_from_image``
        but returns structured ``Block`` objects instead of raw text.
        """
        import cv2

        from docmirror.models.entities.physical import Block

        is_image = file_path.suffix.lower() in CoreExtractor._IMAGE_SUFFIXES
        if not is_image:
            return [], []

        img = cv2.imread(str(file_path))
        if img is None:
            logger.warning("[QGE] OpenCV failed to read image for fallback OCR")
            return [], []

        # Image preprocessing: deskew + CLAHE + sharpen for blurry/skewed images
        try:
            img = CoreExtractor._preprocess_ocr_image(img)
        except Exception as exc:
            logger.debug("[QGE] Image preprocessing skipped: %s", exc)

        try:
            from docmirror.ocr.vision.rapidocr_engine import get_ocr_engine

            engine = get_ocr_engine()
            words = engine.detect_image_words(img)
        except Exception as exc:
            logger.warning(f"[QGE] RapidOCR fallback failed: {exc}")
            return [], []

        if not words:
            logger.info("[QGE] RapidOCR fallback returned no words")
            return [], []

        # ── Two-pass clustering ──
        # Pass 1: Group words into Y-lines by vertical proximity
        sorted_words = sorted(words, key=lambda ww: (ww[1], ww[0]))
        y_lines: list[list] = []
        current_line: list = [sorted_words[0]]
        for ww in sorted_words[1:]:
            prev = current_line[-1]
            # Vertical threshold: max(4px, 1.5× word height)
            if abs(ww[1] - prev[1]) < max(4, (prev[3] - prev[1]) * 1.5):
                current_line.append(ww)
            else:
                y_lines.append(current_line)
                current_line = [ww]
        if current_line:
            y_lines.append(current_line)

        # Pass 2: Column-aware splitting within each Y-line using GCR.
        # Uses the universal Geometry Column Reconstruction algorithm (Otsu-like
        # adaptive threshold) instead of the old fixed max(median_gap*4, 60) rule.
        from docmirror.ocr.reconstruct.gcr import GCRColumns

        column_blocks: list[list] = []
        for line_words in y_lines:
            line_sorted = sorted(line_words, key=lambda ww: ww[0])
            if len(line_sorted) < 2:
                column_blocks.append(line_sorted)
                continue

            # GCRColumns.split_line() accepts any objects with x0/x1/bbox access
            # -- word tuples (x0,y0,x1,y1,text,conf) have element indexing
            col_groups = GCRColumns.split_line(line_sorted)

            if col_groups and len(col_groups) > 0:
                column_blocks.extend(col_groups)
            else:
                column_blocks.append(line_sorted)

        blocks: list[Block] = []
        for i, word_group in enumerate(column_blocks):
            texts = [ww[4] for ww in word_group if ww[4].strip()]
            if not texts:
                continue
            content = " ".join(texts)
            min_x = min(ww[0] for ww in word_group)
            min_y = min(ww[1] for ww in word_group)
            max_x = max(ww[2] for ww in word_group)
            max_y = max(ww[3] for ww in word_group)
            avg_conf = sum(ww[5] if len(ww) > 5 else 0.9 for ww in word_group) / len(word_group)

            blocks.append(
                Block(
                    block_id=f"qge_{i}",
                    block_type="text",
                    bbox=(min_x, min_y, max_x, max_y),
                    reading_order=i,
                    page=1,
                    raw_content=content,
                    attrs={"ocr_source": "qge_fallback", "confidence": round(avg_conf, 3)},
                )
            )

        # Also build OCRToken evidence for the GA1.0 evidence bus
        qge_tokens: list[dict] = []
        from docmirror.ocr.micro_grid.models import OCRToken as _OCRToken

        for idx, ww in enumerate(words):
            token_text = str(ww[4] or "").strip()
            if not token_text:
                continue
            qge_tokens.append(
                _OCRToken(
                    token_id=f"qge_p1_t{idx}",
                    text=token_text,
                    bbox=(float(ww[0]), float(ww[1]), float(ww[2]), float(ww[3])),
                    confidence=float(ww[5]) if len(ww) > 5 else 0.9,
                    page=1,
                    source="qge_fallback",
                    coordinate_system="image_pixels",
                ).to_dict()
            )

        logger.info(
            f"[QGE] Plain OCR fallback: {len(blocks)} text blocks, {len(qge_tokens)} OCR tokens from {len(words)} words"
        )
        return blocks, qge_tokens

    @staticmethod
    def _qge_build_pages_from_blocks(ocr_blocks: list[Block]) -> tuple[list, str]:
        """Build PageLayout list and full_text from raw OCR blocks.

        Used by the direct-path optimization (skip scanned pipeline).
        Returns (pages, full_text) matching the shape expected downstream.
        """
        from docmirror.models.entities.physical import PageLayout

        if not ocr_blocks:
            return [], ""

        full_text = "\n".join((b.raw_content if isinstance(b.raw_content, str) else "") for b in ocr_blocks)
        page = PageLayout(
            page_number=1,
            blocks=tuple(ocr_blocks),
            is_scanned=True,
        )
        return [page], full_text

    @staticmethod
    def _qge_merge_results(pages: list, full_text: str, ocr_blocks: list[Block]) -> tuple[list, str, int, int]:
        """Merge plain-OCR blocks into the first page when it has little text.

        Strategy:
        1. Find the first page with few or no text blocks.
        2. Replace its text blocks with the OCR fallback blocks.
        3. Keep all tables/key_values from the original page.
        4. Recalculate full_text to include OCR text.

        Returns (updated_pages, updated_full_text, table_count, total_blocks).
        """
        if not ocr_blocks or not pages:
            return pages, full_text, 0, 0

        new_pages = list(pages)
        target_page = new_pages[0]

        text_blocks = [b for b in target_page.blocks if b.block_type == "text"]
        if len(text_blocks) >= 3:
            logger.debug("[QGE] Page already has sufficient text blocks, skipping merge")
            return pages, full_text, 0, 0

        kept_blocks = [b for b in target_page.blocks if b.block_type != "text"]
        import dataclasses

        merged_page = dataclasses.replace(
            target_page,
            blocks=tuple(kept_blocks + ocr_blocks),
        )
        new_pages[0] = merged_page

        ocr_text = "\n".join((b.raw_content if isinstance(b.raw_content, str) else "") for b in ocr_blocks)
        merged_full_text = full_text
        if ocr_text:
            merged_full_text = (full_text + "\n\n" + ocr_text).strip()

        total_blocks_new = sum(len(p.blocks) for p in new_pages)
        table_count_new = sum(1 for p in new_pages for b in p.blocks if b.block_type == "table")

        logger.info(
            f"[QGE] Merged {len(ocr_blocks)} OCR blocks | tables={table_count_new} | text_len={len(merged_full_text)}"
        )
        return new_pages, merged_full_text, table_count_new, total_blocks_new

    def _assess_extraction_quality(self, pages, extraction_layer: str, extraction_confidence: float) -> dict[str, Any]:
        """Assess extraction quality for the main table."""
        table_count = sum(1 for p in pages for b in p.blocks if b.block_type == "table")
        if table_count == 0:
            return {"extraction_layer": extraction_layer, "extraction_confidence": extraction_confidence}

        # Find main table (largest table block)
        main_table = None
        for p in pages:
            for b in p.blocks:
                if b.block_type == "table" and isinstance(b.raw_content, list):
                    if main_table is None or len(b.raw_content) > len(main_table):
                        main_table = b.raw_content

        header_detected = False
        data_row_count = 0
        col_count_stable = True
        empty_cell_ratio = 0.0

        if main_table and len(main_table) >= 2:
            header_detected = _is_header_row(main_table[0])
            data_row_count = len(main_table) - 1
            expected_cols = len(main_table[0])
            col_count_stable = all(len(row) == expected_cols for row in main_table)
            total_cells = sum(len(row) for row in main_table)
            empty_cells = sum(1 for row in main_table for c in row if not (c or "").strip())
            empty_cell_ratio = round(empty_cells / max(1, total_cells), 3)

        return {
            "extraction_layer": extraction_layer,
            "extraction_confidence": extraction_confidence,
            "header_detected": header_detected,
            "data_row_count": data_row_count,
            "col_count_stable": col_count_stable,
            "empty_cell_ratio": empty_cell_ratio,
            "layer_timings_ms": get_last_layer_timings(),
        }

    def _process_pdf_sync(
        self, fitz_doc, pre_analysis, has_text, is_image_input, cleaned_path, file_path, options=None
    ):
        raise NotImplementedError("raw PdfSyncProcessor was removed; use CoreExtractor.extract() or MirrorCoreVNext")

    def _extract_page(self, ctx):
        raise NotImplementedError("raw PageExtractor was removed; use the UDTR pipeline")

    def _extract_scanned_page(self, **kwargs):
        raise NotImplementedError("raw scanned page extractor was removed; use the UDTR pipeline")

    def _collect_kv_entities(self, pages):
        return collect_kv_entities(pages)

    def _post_process_tables(self, pages, extraction_profile=None):
        return process_page_tables(pages, extraction_profile=extraction_profile)
