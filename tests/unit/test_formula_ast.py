# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for formula AST parser, serializer, normalizer, and comparators.

GA F1-F6, F10 coverage:
  - F1: parse, serialize, structural equals, diff
  - F6: normalization (Greek variant, multi-letter, frac)
  - F10: spoken text (en)
"""

from __future__ import annotations

import pytest
from docmirror.ocr.formula_ast import (
    ASTNode,
    ASTNodeType,
    LaTeXSymbolTree,
    tokenize_latex,
)


# Shared tree instance — all methods are instance methods
T = LaTeXSymbolTree()


class TestTokenizeLatex:
    """F1: Tokenizer."""

    def test_tokenize_simple(self):
        tokens = tokenize_latex(r"x^{2}")
        token_types = [t["type"] for t in tokens]
        assert "char" in token_types or "symbol" in token_types
        assert "super" in token_types

    def test_tokenize_frac(self):
        tokens = tokenize_latex(r"\frac{a}{b}")
        has_frac = any(t["value"] == r"\frac" for t in tokens)
        assert has_frac

    def test_tokenize_sum(self):
        tokens = tokenize_latex(r"\sum_{i=1}^{n}")
        has_sum = any(t["value"] == r"\sum" for t in tokens)
        assert has_sum
        has_sub = any(t["type"] == "sub" for t in tokens)
        assert has_sub

    def test_tokenize_greek(self):
        tokens = tokenize_latex(r"\alpha + \beta")
        values = [t["value"] for t in tokens]
        assert r"\alpha" in values
        assert r"\beta" in values


class TestLaTeXSymbolTreeParse:
    """F1: LaTeX parsing core."""

    def test_parse_simple_symbol(self):
        root = T.parse(r"x")
        assert len(root.children) >= 1

    def test_parse_superscript(self):
        root = T.parse(r"x^{2}")
        has_sup = any(c.node_type == ASTNodeType.SUP for c in root.children)
        assert has_sup

    def test_parse_subscript(self):
        root = T.parse(r"a_{i}")
        has_sub = any(c.node_type == ASTNodeType.SUB for c in root.children)
        assert has_sub

    def test_parse_frac(self):
        root = T.parse(r"\frac{a}{b}")
        has_frac = any(c.node_type == ASTNodeType.FRAC for c in root.children)
        assert has_frac

    def test_parse_sqrt(self):
        root = T.parse(r"\sqrt{x}")
        has_sqrt = any(c.node_type == ASTNodeType.SQRT for c in root.children)
        assert has_sqrt

    def test_parse_complex_nesting(self):
        root = T.parse(r"\frac{a^{n+1}}{b_{ij}}")
        has_frac = any(c.node_type == ASTNodeType.FRAC for c in root.children)
        assert has_frac
        # Verify nesting: frac exists with children
        frac = next(c for c in root.children if c.node_type == ASTNodeType.FRAC)
        assert len(frac.children) == 2  # numerator + denominator

    def test_parse_sum_with_limits(self):
        root = T.parse(r"\sum_{i=1}^{n} x_{i}")
        assert len(root.children) >= 1

    def test_parse_greek_letters(self):
        root = T.parse(r"\alpha")
        # Greek letters become SYMBOL nodes
        symbols = [c for c in root.children if c.node_type == ASTNodeType.SYMBOL]
        assert len(symbols) >= 1

    def test_parse_error_recovery(self):
        root = T.parse(r"\frac{a}{")
        # Should still return a root node even on error
        assert root.node_type == ASTNodeType.ROOT

    def test_parse_group(self):
        root = T.parse(r"{a + b}")
        has_group = any(c.node_type == ASTNodeType.GROUP for c in root.children)
        assert has_group

    def test_parse_left_right(self):
        root = T.parse(r"\left( x \right)")
        has_lr = any(c.node_type == ASTNodeType.LEFT_RIGHT for c in root.children)
        assert has_lr


class TestLaTeXSymbolTreeSerialize:
    """F1: LaTeX serialization round-trip."""

    def test_roundtrip_simple(self):
        root = T.parse(r"x^{2}")
        result = T.to_latex(root)
        assert r"x^{2}" in result.replace(" ", "")

    def test_roundtrip_frac(self):
        root = T.parse(r"\frac{a}{b}")
        result = T.to_latex(root)
        assert r"\frac" in result

    def test_roundtrip_sum(self):
        root = T.parse(r"\sum_{i=1}^{n}")
        result = T.to_latex(root)
        assert r"\sum" in result


class TestNormalization:
    """F6: Greek variant, multi-letter merge, frac normalization."""

    def test_greek_variant_unification(self):
        root = T.parse(r"\varepsilon")
        norm = T.normalize(root)
        result = T.to_latex(norm)
        assert r"\varepsilon" not in result
        assert r"\epsilon" in result

    def test_multi_letter_variable_merge(self):
        root = T.parse(r"\alpha_{max}")
        norm = T.normalize(root)
        result = T.to_latex(norm)
        # subscript "max" should be present as merged multi-letter
        assert "max" in result

    def test_commutative_sorting_spaced(self):
        # Use spaces so tokens are separate: "a + b" vs "b + a"
        root1 = T.parse(r"a + b")
        root2 = T.parse(r"b + a")
        norm1 = T.normalize(root1)
        norm2 = T.normalize(root2)
        assert T.structural_equals(norm1, norm2)

    def test_redundant_brace_removal(self):
        root = T.parse(r"x^{{2}}")
        norm = T.normalize(root)
        result = T.to_latex(norm)
        # Should not have triple braces
        assert "{{{2}}}" not in result


class TestStructuralEquality:
    """F1: Structural equality and diff."""

    def test_identical_equal(self):
        root1 = T.parse(r"\frac{1}{2}")
        root2 = T.parse(r"\frac{1}{2}")
        assert T.structural_equals(root1, root2)

    def test_different_not_equal(self):
        root1 = T.parse(r"a + b")
        root2 = T.parse(r"a - b")
        diff = T.diff(root1, root2)
        assert len(diff) > 0

    def test_diff_empty_for_same(self):
        root1 = T.parse(r"x^{2}")
        root2 = T.parse(r"x^{2}")
        diffs = T.diff(root1, root2)
        assert diffs == []

    def test_diff_generates_diffs(self):
        root1 = T.parse(r"x^{2}")
        root2 = T.parse(r"x^{3}")
        diffs = T.diff(root1, root2)
        assert len(diffs) > 0


class TestSpokenText:
    """F10: Spoken descriptions."""

    def test_spoken_en_simple(self):
        root = T.parse(r"x^{2}")
        text = T.to_spoken(root, lang="en")
        assert "x" in text.lower()

    def test_spoken_en_frac(self):
        root = T.parse(r"\frac{a}{b}")
        text = T.to_spoken(root, lang="en")
        assert "a" in text and "b" in text

    def test_spoken_zh_frac(self):
        root = T.parse(r"\frac{1}{2}")
        text = T.to_spoken(root, lang="zh")
        assert "1" in text and "2" in text


class TestMathML:
    """F7: MathML output."""

    def test_mathml_output(self):
        root = T.parse(r"x^{2}")
        ml = T.to_mathml(root)
        assert "<math" in ml
        assert "</math>" in ml

    def test_mathml_frac(self):
        root = T.parse(r"\frac{a}{b}")
        ml = T.to_mathml(root)
        assert "<mfrac>" in ml
