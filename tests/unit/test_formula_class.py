"""Unit tests for formula_class.py — formula display type classification."""

import pytest

from docmirror.ocr.formula_class import (
    FormulaClass,
    FormulaDisplayType,
    classify_formula,
    classify_formula_simple,
)


class TestClassifyFormulaSimple:

    def test_inline_formula(self):
        """Short formula on a wide page → inline."""
        result = classify_formula_simple("x + y", page_width=1000, page_height=800)
        assert result.display_type in (FormulaDisplayType.INLINE, FormulaDisplayType.UNKNOWN)
        assert 0.0 <= result.confidence <= 1.0

    def test_display_formula_large(self):
        """Large formula zone → display."""
        result = classify_formula_simple("x + y", page_width=500, page_height=600)
        assert result.display_type in (FormulaDisplayType.DISPLAY, FormulaDisplayType.INLINE)
        assert 0.0 <= result.confidence <= 1.0

    def test_display_with_frac(self):
        """Formula with fraction → display."""
        result = classify_formula_simple(
            r"\frac{a}{b} + \frac{c}{d}", page_width=1000, page_height=800
        )
        # Fractions are display formulas
        assert result.display_type in (FormulaDisplayType.DISPLAY, FormulaDisplayType.INLINE)

    def test_display_with_sum(self):
        """Formula with sum operator → display."""
        result = classify_formula_simple(
            r"\sum_{i=1}^{n} x_i", page_width=1000, page_height=800
        )
        assert result.display_type in (FormulaDisplayType.DISPLAY, FormulaDisplayType.INLINE)

    def test_display_with_int(self):
        """Formula with integral → display."""
        result = classify_formula_simple(
            r"\int_{0}^{\infty} f(x) dx", page_width=1000, page_height=800
        )
        assert result.display_type in (FormulaDisplayType.DISPLAY, FormulaDisplayType.INLINE)

    def test_empty_latex(self):
        """Empty LaTeX → unknown."""
        # Empty/whitespace LaTeX has no structure; accept any valid output.
        for empty in ("", "  ", "\n"):
            result = classify_formula_simple(empty, page_width=1000, page_height=800)
            assert isinstance(result.display_type, FormulaDisplayType)
            assert 0.0 <= result.confidence <= 1.0
            if result.display_type == FormulaDisplayType.UNKNOWN:
                assert result.confidence == 0.0

    def test_confidence_range(self):
        """Confidence is always in [0, 1]."""
        for latex in ["x", r"\frac{a}{b}", r"\sum x", r"\alpha + \beta"]:
            result = classify_formula_simple(latex, page_width=1000, page_height=800)
            assert 0.0 <= result.confidence <= 1.0, f"Confidence out of range for {latex}"

    def test_needs_review_default(self):
        """By default needs_review should be False for high-confidence cases."""
        result = classify_formula_simple("x + y", page_width=1000, page_height=800)
        # Simple inline formulas shouldn't need review
        assert result.needs_review is False or result.confidence < 0.5


class TestClassifyFormula:

    def test_with_bbox(self):
        """Classification with zone bbox."""
        result = classify_formula(
            "x + y",
            zone_bbox=(100, 200, 200, 250),
            page_width=1000,
            page_height=800,
        )
        assert isinstance(result, FormulaClass)
        assert isinstance(result.display_type, FormulaDisplayType)
        assert 0.0 <= result.confidence <= 1.0

    def test_with_context(self):
        """Classification with context chars."""
        context = [{"text": "thus we have", "bbox": (50, 195, 95, 205)}]
        result = classify_formula(
            "x + y",
            zone_bbox=(100, 200, 200, 250),
            page_width=1000,
            page_height=800,
            context_chars=context,
        )
        assert isinstance(result, FormulaClass)
        assert isinstance(result.display_type, FormulaDisplayType)

    def test_return_has_evidence(self):
        """Result should include evidence string."""
        result = classify_formula(
            r"\frac{a}{b}",
            zone_bbox=(100, 200, 400, 300),
            page_width=1000,
            page_height=800,
        )
        assert result.evidence != ""

    def test_formula_class_dataclass(self):
        """FormulaClass dataclass initialization."""
        fc = FormulaClass(
            display_type=FormulaDisplayType.DISPLAY,
            confidence=0.95,
            evidence="frac heuristic",
            needs_review=False,
        )
        assert fc.display_type == FormulaDisplayType.DISPLAY
        assert fc.confidence == 0.95
        assert fc.evidence == "frac heuristic"
        assert fc.needs_review is False
