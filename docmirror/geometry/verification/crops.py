"""Generate verification unit crop artifacts for visual/OCR review."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

_DEFAULT_MAX_CROPS = 200
_SUPPORTED_UNIT_TYPES = {"table_cell", "kv_field"}
CropOCRRunner = Callable[[Path, dict[str, Any]], dict[str, Any] | None]


def attach_verification_crop_assets(
    mirror: dict[str, Any],
    *,
    pdf_path: str | Path,
    task_dir: str | Path,
    max_crops: int = _DEFAULT_MAX_CROPS,
    asset_subdir: str = "assets/verification_crops",
) -> list[dict[str, Any]]:
    """Write PNG crops for sampled verification units and attach them to assets."""
    source_path = Path(pdf_path)
    if not source_path.exists() or source_path.suffix.lower() != ".pdf":
        _append_diagnostics(mirror, status="not_applicable", reason="source_is_not_pdf")
        return []
    units = _verification_units(mirror)
    if not units:
        _append_diagnostics(mirror, status="not_applicable", reason="no_verification_units")
        return []

    try:
        import fitz
    except ImportError:
        _append_diagnostics(mirror, status="not_applicable", reason="pymupdf_not_available")
        return []

    task_path = Path(task_dir)
    relative_dir = Path(asset_subdir)
    crop_dir = task_path / relative_dir
    pages_by_id = _pages_by_id(mirror)
    generated: list[dict[str, Any]] = []
    requested_count = 0

    try:
        doc = fitz.open(str(source_path))
    except Exception as exc:
        _append_diagnostics(mirror, status="warn", reason=f"pdf_open_failed:{exc}")
        return []

    try:
        for unit in units:
            if len(generated) >= max_crops:
                break
            if unit.get("unit_type") not in _SUPPORTED_UNIT_TYPES:
                continue
            if not str(unit.get("selected_value") or "").strip():
                continue
            page_id = _first_page_id(unit)
            page = pages_by_id.get(page_id)
            bbox = _bbox(unit.get("bbox"))
            if not page or not bbox:
                continue
            page_number = _page_number(page)
            if page_number < 1 or page_number > len(doc):
                continue
            source_bbox = _source_bbox(bbox, page)
            if not source_bbox:
                continue
            requested_count += 1
            rect = _fitz_rect(fitz, source_bbox, doc[page_number - 1].rect)
            if rect is None:
                continue
            crop_dir.mkdir(parents=True, exist_ok=True)
            asset_id = f"asset:verification_crop:{len(generated) + 1:06d}"
            file_name = f"{_safe_filename(asset_id)}.png"
            relative_path = relative_dir / file_name
            pix = doc[page_number - 1].get_pixmap(clip=rect, dpi=160)
            pix.save(str(task_path / relative_path))
            item = {
                "id": asset_id,
                "kind": "verification_unit_crop",
                "media_type": "image/png",
                "path": relative_path.as_posix(),
                "generator": "verification_crop_artifact_v1",
                "purpose": "unit_crop_ocr_seed",
                "unit_id": str(unit.get("unit_id") or ""),
                "unit_type": str(unit.get("unit_type") or ""),
                "block_id": str(unit.get("block_id") or ""),
                "page_id": page_id,
                "page_number": page_number,
                "bbox": bbox,
                "source_bbox": source_bbox,
                "evidence_ids": list(unit.get("evidence_ids") or []),
                "selected_value": unit.get("selected_value"),
            }
            generated.append(item)
    finally:
        doc.close()

    if generated:
        assets = mirror.setdefault("assets", {}).setdefault("items", [])
        assets.extend(generated)
        verification = mirror.setdefault("quality", {}).setdefault("verification", {})
        verification["crop_artifact_count"] = len(generated)
        verification["crop_artifact_dir"] = asset_subdir
    _append_diagnostics(
        mirror,
        status="ok" if generated else "not_applicable",
        generated_count=len(generated),
        requested_count=requested_count,
        max_crops=max_crops,
        asset_subdir=asset_subdir,
        reason="" if generated else "no_supported_units_to_crop",
    )
    return generated


def attach_unit_crop_ocr_candidates(
    mirror: dict[str, Any],
    *,
    task_dir: str | Path,
    crop_assets: list[dict[str, Any]] | None = None,
    ocr_runner: CropOCRRunner | None = None,
    max_ocr_crops: int = 50,
    min_confidence: float = 0.75,
) -> dict[str, Any]:
    """Run OCR on verification crops and attach OCR candidates to sampled units."""
    assets = crop_assets if crop_assets is not None else _verification_crop_assets(mirror)
    if not assets:
        summary = _crop_ocr_summary(status="not_applicable", reason="no_verification_crop_assets")
        _attach_crop_ocr_summary(mirror, summary)
        return summary
    runner = ocr_runner or _default_crop_ocr_runner
    task_path = Path(task_dir)
    unit_by_id = _verification_unit_by_id(mirror)
    processed = 0
    candidate_count = 0
    agreement_count = 0
    conflict_count = 0
    not_evaluated_count = 0
    claim_items: list[dict[str, Any]] = []

    for asset in assets[:max_ocr_crops]:
        unit_id = str(asset.get("unit_id") or "")
        unit = unit_by_id.get(unit_id)
        crop_path = task_path / str(asset.get("path") or "")
        if not unit or not crop_path.exists():
            continue
        processed += 1
        try:
            ocr = runner(crop_path, asset) or {}
        except Exception as exc:
            ocr = {"status": "not_evaluated", "reason": f"ocr_failed:{exc}"}
        text = str(ocr.get("text") or "").strip()
        confidence = _float(ocr.get("confidence"), 0.0)
        engine = str(ocr.get("engine") or "unknown")
        status = "not_evaluated"
        reasons: list[str] = []
        if text and confidence >= min_confidence:
            candidate_count += 1
            selected_value = unit.get("selected_value")
            if _values_agree(selected_value, text):
                status = "verified"
                agreement_count += 1
            else:
                status = "requires_review"
                conflict_count += 1
                reasons.append("unit_crop_ocr_value_mismatch")
            _append_unit_crop_candidate(unit, asset, text=text, confidence=confidence, engine=engine)
        else:
            not_evaluated_count += 1
            reasons.append(str(ocr.get("reason") or "low_confidence_or_empty_ocr"))
        asset["ocr"] = {
            "status": status,
            "engine": engine,
            "text": text,
            "confidence": confidence,
            "reasons": reasons,
        }
        claim_items.append(
            {
                "claim_id": f"claim:{unit_id}:unit_crop_ocr_vote",
                "claim_type": "unit_crop_ocr_vote",
                "subject_unit_id": unit_id,
                "status": status,
                "score": confidence if status == "verified" else 0.0,
                "evidence_ids": list(unit.get("evidence_ids") or []),
                "reasons": reasons,
            }
        )

    summary = _crop_ocr_summary(
        status="ok" if processed else "not_applicable",
        processed_count=processed,
        candidate_count=candidate_count,
        agreement_count=agreement_count,
        conflict_count=conflict_count,
        not_evaluated_count=not_evaluated_count,
        max_ocr_crops=max_ocr_crops,
        min_confidence=min_confidence,
    )
    _attach_crop_ocr_summary(mirror, summary, claim_items=claim_items)
    return summary


def _verification_units(mirror: dict[str, Any]) -> list[dict[str, Any]]:
    units = ((mirror.get("quality") or {}).get("verification") or {}).get("units") or []
    return [unit for unit in units if isinstance(unit, dict)]


def _verification_unit_by_id(mirror: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(unit.get("unit_id") or ""): unit for unit in _verification_units(mirror)}


def _verification_crop_assets(mirror: dict[str, Any]) -> list[dict[str, Any]]:
    assets = (mirror.get("assets") or {}).get("items") or []
    return [asset for asset in assets if isinstance(asset, dict) and asset.get("kind") == "verification_unit_crop"]


def _pages_by_id(mirror: dict[str, Any]) -> dict[str, dict[str, Any]]:
    pages = mirror.get("pages") or []
    return {str(page.get("page_id") or ""): page for page in pages if isinstance(page, dict)}


def _first_page_id(unit: dict[str, Any]) -> str:
    page_ids = unit.get("page_ids") or []
    if not page_ids:
        return ""
    return str(page_ids[0])


def _page_number(page: dict[str, Any]) -> int:
    try:
        return int(page.get("page_number") or int(page.get("page_index") or 0) + 1)
    except (TypeError, ValueError):
        return 0


def _source_bbox(bbox: list[float], page: dict[str, Any]) -> list[float] | None:
    transform = page.get("coordinate_transform") if isinstance(page.get("coordinate_transform"), dict) else {}
    matrix = transform.get("inverse_matrix") if isinstance(transform, dict) else None
    if not _is_matrix(matrix):
        return bbox
    points = [
        _apply_matrix(matrix, bbox[0], bbox[1]),
        _apply_matrix(matrix, bbox[2], bbox[1]),
        _apply_matrix(matrix, bbox[2], bbox[3]),
        _apply_matrix(matrix, bbox[0], bbox[3]),
    ]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _fitz_rect(fitz: Any, bbox: list[float], page_rect: Any, *, padding: float = 2.0) -> Any | None:
    x0 = max(float(page_rect.x0), bbox[0] - padding)
    y0 = max(float(page_rect.y0), bbox[1] - padding)
    x1 = min(float(page_rect.x1), bbox[2] + padding)
    y1 = min(float(page_rect.y1), bbox[3] + padding)
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    return fitz.Rect(x0, y0, x1, y1)


def _append_diagnostics(
    mirror: dict[str, Any],
    *,
    status: str,
    reason: str = "",
    generated_count: int = 0,
    requested_count: int = 0,
    max_crops: int = _DEFAULT_MAX_CROPS,
    asset_subdir: str = "assets/verification_crops",
) -> None:
    diagnostics = mirror.setdefault("diagnostics", {}).setdefault("pipeline", [])
    entry = {
        "stage": "verification_crop_artifacts",
        "status": status,
        "generated_count": generated_count,
        "requested_count": requested_count,
        "max_crops": max_crops,
        "asset_subdir": asset_subdir,
    }
    if reason:
        entry["reason"] = reason
    diagnostics.append(entry)


def _default_crop_ocr_runner(crop_path: Path, _asset: dict[str, Any]) -> dict[str, Any] | None:
    try:
        import cv2

        from docmirror.ocr.vision.rapidocr_engine import get_ocr_engine

        img = cv2.imread(str(crop_path))
        if img is None:
            return {"status": "not_evaluated", "reason": "image_read_failed"}
        words = get_ocr_engine().detect_image_words(img, multi_scale=False)
        text_items = [str(word[4]).strip() for word in words if len(word) >= 5 and str(word[4]).strip()]
        confidences = [float(word[8]) for word in words if len(word) >= 9]
        if text_items:
            return {
                "engine": "rapidocr",
                "text": " ".join(text_items),
                "confidence": sum(confidences) / len(confidences) if confidences else 0.8,
            }
    except Exception:
        pass

    try:
        from docmirror.ocr.backends.tesseract import TesseractBackend

        backend = TesseractBackend()
        if not backend.is_available:
            return {"status": "not_evaluated", "engine": "tesseract", "reason": "ocr_backend_unavailable"}
        result = backend.ocr(crop_path.read_bytes(), lang="eng", psm=7, timeout=10)
        return {
            "engine": "tesseract",
            "text": result.text,
            "confidence": result.confidence,
        }
    except Exception as exc:
        return {"status": "not_evaluated", "engine": "fallback", "reason": f"ocr_backend_failed:{exc}"}


def _append_unit_crop_candidate(
    unit: dict[str, Any],
    asset: dict[str, Any],
    *,
    text: str,
    confidence: float,
    engine: str,
) -> None:
    candidates = unit.setdefault("candidates", [])
    candidate = {
        "source": "unit_crop_ocr",
        "value": text,
        "confidence": confidence,
        "evidence_ids": list(unit.get("evidence_ids") or []),
        "metadata": {
            "asset_id": asset.get("id"),
            "asset_path": asset.get("path"),
            "engine": engine,
        },
    }
    key = (candidate["source"], candidate["value"], candidate["metadata"]["asset_id"])
    for existing in candidates:
        existing_key = (
            existing.get("source"),
            existing.get("value"),
            (existing.get("metadata") or {}).get("asset_id"),
        )
        if existing_key == key:
            return
    candidates.append(candidate)


def _attach_crop_ocr_summary(
    mirror: dict[str, Any],
    summary: dict[str, Any],
    *,
    claim_items: list[dict[str, Any]] | None = None,
) -> None:
    verification = mirror.setdefault("quality", {}).setdefault("verification", {})
    verification["crop_ocr"] = summary
    if claim_items:
        claims = verification.setdefault("claims", [])
        existing_ids = {claim.get("claim_id") for claim in claims if isinstance(claim, dict)}
        for claim in claim_items:
            if claim["claim_id"] not in existing_ids:
                claims.append(claim)
                existing_ids.add(claim["claim_id"])
    gate_status = "not_applicable"
    gate_score = 1.0
    if summary.get("processed_count", 0):
        gate_status = "pass"
        gate_score = summary.get("agreement_count", 0) / max(summary.get("candidate_count", 0), 1)
    gates = mirror.setdefault("quality", {}).setdefault("gates", [])
    gates.append(
        {
            "id": "gate:verification_crop_ocr",
            "status": gate_status,
            "score": gate_score,
            "threshold": 0.0,
            "details": summary,
        }
    )
    diagnostics = mirror.setdefault("diagnostics", {}).setdefault("pipeline", [])
    diagnostics.append({"stage": "verification_crop_ocr", **summary})


def _crop_ocr_summary(
    *,
    status: str,
    reason: str = "",
    processed_count: int = 0,
    candidate_count: int = 0,
    agreement_count: int = 0,
    conflict_count: int = 0,
    not_evaluated_count: int = 0,
    max_ocr_crops: int = 50,
    min_confidence: float = 0.75,
) -> dict[str, Any]:
    summary = {
        "status": status,
        "processed_count": processed_count,
        "candidate_count": candidate_count,
        "agreement_count": agreement_count,
        "conflict_count": conflict_count,
        "not_evaluated_count": not_evaluated_count,
        "max_ocr_crops": max_ocr_crops,
        "min_confidence": min_confidence,
    }
    if reason:
        summary["reason"] = reason
    return summary


def _values_agree(selected_value: Any, ocr_text: str) -> bool:
    selected = str(selected_value if selected_value is not None else "").strip()
    text = str(ocr_text or "").strip()
    if not selected or not text:
        return False
    selected_number = _parse_number(selected)
    ocr_number = _parse_number(text)
    if selected_number is not None and ocr_number is not None:
        if abs(selected_number - ocr_number) < 1e-9:
            return True
        selected_digits = _digits(selected)
        if len(selected_digits) >= 8:
            return _character_coverage_agrees(selected_digits, _digits(text), max_extra_ratio=1.35)
        return False
    if selected_number is not None:
        return _character_coverage_agrees(_digits(selected), _digits(text), max_extra_ratio=1.35)
    selected_compact = _compact_text(selected)
    text_compact = _compact_text(text)
    return selected_compact == text_compact or _character_coverage_agrees(
        selected_compact,
        text_compact,
        max_extra_ratio=1.45,
    )


def _parse_number(value: str) -> float | None:
    cleaned = str(value or "").strip().replace(",", "").replace("，", "")
    if not cleaned or not re.search(r"\d", cleaned):
        return None
    if (cleaned.startswith("(") and cleaned.endswith(")")) or (cleaned.startswith("（") and cleaned.endswith("）")):
        cleaned = f"-{cleaned[1:-1]}"
    if re.search(r"\d\s+\d", cleaned):
        return None
    match = re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned)
    return float(match.group(0)) if match else None


def _compact_text(value: str) -> str:
    return re.sub(r"[\s,，。.:：;；、]+", "", value.strip())


def _digits(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def _character_coverage_agrees(expected: str, observed: str, *, max_extra_ratio: float) -> bool:
    expected = expected.strip()
    observed = observed.strip()
    if not expected or not observed:
        return False
    if expected == observed:
        return True
    from collections import Counter

    expected_counts = Counter(expected)
    observed_counts = Counter(observed)
    covered = sum(min(count, observed_counts.get(char, 0)) for char, count in expected_counts.items())
    coverage = covered / max(sum(expected_counts.values()), 1)
    extra_ratio = len(observed) / max(len(expected), 1)
    return coverage >= 0.95 and extra_ratio <= max_extra_ratio


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bbox(value: Any) -> list[float] | None:
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    try:
        x0, y0, x1, y1 = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


def _is_matrix(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 3 and all(isinstance(row, list) and len(row) == 3 for row in value)


def _apply_matrix(matrix: list[list[float]], x: float, y: float) -> tuple[float, float]:
    return (
        float(matrix[0][0]) * x + float(matrix[0][1]) * y + float(matrix[0][2]),
        float(matrix[1][0]) * x + float(matrix[1][1]) * y + float(matrix[1][2]),
    )


def _safe_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_") or "verification_crop"
