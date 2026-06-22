"""OCR Quality Gate — W2-01 of the Failure & Degradation Contract.

Monitors OCR confidence, text density, language/garbled score, and table
extraction confidence per page. Emits ``OutcomeEvent`` entries when quality
falls below configured thresholds so low-quality results are never silent.

Usage::

    from docmirror.quality.ocr_quality_outcome import OcrQualityGate, PageQualityInput

    gate = OcrQualityGate()
    quality = gate.evaluate_page(PageQualityInput(
        page=3,
        ocr_confidence=0.42,
        text_density=0.15,
    ))
    if quality.outcome:
        ledger.add_event(quality.outcome)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from docmirror.models.outcome import OutcomeEvent
from docmirror.models.outcome_bridge import _make_outcome_event


@dataclass
class PageQualityInput:
    """Per-page quality signals fed into the OCR Quality Gate."""

    page: int
    ocr_confidence: float | None = None          # 0.0 - 1.0
    text_density: float | None = None             # 0.0 - 1.0
    garbled_score: float | None = None            # 0.0 - 1.0 (higher = more garbled)
    table_confidence: float | None = None         # 0.0 - 1.0
    image_dpi: int | None = None
    image_dimensions: tuple[int, int] | None = None
    has_text_layer: bool = True
    source: str = "ocr_engine"


@dataclass
class PageQualityResult:
    """Output of the OCR Quality Gate for one page."""

    page: int
    quality_bucket: str = "acceptable"       # excellent / acceptable / low_quality / unreadable
    overall_confidence: float = 1.0
    outcome: OutcomeEvent | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


class OcrQualityGate:
    """Evaluates per-page OCR quality and emits outcome events.

    Thresholds are configurable via constructor. Default thresholds follow
    the GA quality targets defined in ``quality/ga_metrics.py``.
    """

    def __init__(
        self,
        low_confidence_threshold: float = 0.65,
        unreadable_threshold: float = 0.30,
        low_text_density_threshold: float = 0.05,
        garbled_threshold: float = 0.50,
        min_recommended_dpi: int = 150,
    ) -> None:
        self.low_confidence_threshold = low_confidence_threshold
        self.unreadable_threshold = unreadable_threshold
        self.low_text_density_threshold = low_text_density_threshold
        self.garbled_threshold = garbled_threshold
        self.min_recommended_dpi = min_recommended_dpi

    def evaluate_page(self, page_input: PageQualityInput) -> PageQualityResult:
        """Evaluate one page and return quality bucket + optional outcome event."""
        confidence = page_input.ocr_confidence or 0.0
        text_density = page_input.text_density
        garbled = page_input.garbled_score or 0.0

        # Determine quality bucket
        if confidence < self.unreadable_threshold:
            bucket = "unreadable"
        elif confidence < self.low_confidence_threshold:
            bucket = "low_quality"
        elif text_density is not None and text_density < self.low_text_density_threshold:
            bucket = "low_quality"
        elif garbled > self.garbled_threshold:
            bucket = "low_quality"
        else:
            bucket = "acceptable"
        if confidence >= 0.85:
            bucket = "excellent"

        result = PageQualityResult(
            page=page_input.page,
            quality_bucket=bucket,
            overall_confidence=confidence,
            metrics={
                "ocr_confidence": confidence,
                "text_density": text_density,
                "garbled_score": garbled,
                "table_confidence": page_input.table_confidence,
                "image_dpi": page_input.image_dpi,
                "threshold_low": self.low_confidence_threshold,
                "threshold_unreadable": self.unreadable_threshold,
            },
        )

        # Emit outcome for low-quality or unreadable pages
        if bucket in ("low_quality", "unreadable"):
            canonical = "LOW_OCR_CONFIDENCE" if bucket == "low_quality" else "LOW_QUALITY_INPUT"
            suggestion = ""
            if confidence < self.low_confidence_threshold:
                suggestion = "Retry with profile=forensic or rescan affected pages at 300 DPI or higher."
            elif garbled > self.garbled_threshold:
                suggestion = "Text appears garbled. Verify correct language/layout or rescan with higher quality."
            elif page_input.image_dpi and page_input.image_dpi < self.min_recommended_dpi:
                suggestion = f"Image resolution is {page_input.image_dpi} DPI. Rescan at {self.min_recommended_dpi}+ DPI for better results."

            result.outcome = _make_outcome_event(
                canonical,
                status="partial",
                scope_override={"type": "page", "pages": [page_input.page]},
                details={
                    "observed_confidence": confidence,
                    "threshold": self.low_confidence_threshold,
                    "quality_bucket": bucket,
                    **result.metrics,
                },
                suggestion_override=suggestion,
                source_component="ocr_quality_gate",
                evidence_refs=[f"page:{page_input.page}"],
            )

        return result

    def evaluate_pages(self, page_inputs: list[PageQualityInput]) -> list[PageQualityResult]:
        """Evaluate multiple pages."""
        return [self.evaluate_page(p) for p in page_inputs]

    def summary(self, results: list[PageQualityResult]) -> dict[str, Any]:
        """Aggregate quality results across pages."""
        buckets: dict[str, int] = {}
        affected: list[int] = []
        for r in results:
            buckets[r.quality_bucket] = buckets.get(r.quality_bucket, 0) + 1
            if r.outcome:
                affected.append(r.page)
        return {
            "total_pages": len(results),
            "buckets": buckets,
            "affected_pages": affected,
            "overall_quality": "low_quality" if affected else "acceptable",
        }
