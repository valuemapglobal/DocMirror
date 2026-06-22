# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
MathML exporter — Presentation MathML output from formula AST or LaTeX.

Purpose: Convert formula content (AST or LaTeX) to Presentation MathML for
Office interop, accessibility (screen readers), and W3C compliance.

Design (from 19_formula_recognition_first_principles_redesign.md):
  - FM-7: MathML output
  - Primary path: LaTeX -> AST -> MathML (lossless structural conversion)
  - Fallback path: LaTeX -> MathML via simple text substitution

Main components:
  - export_mathml_from_block(): Export from a formula Block
  - export_mathml_from_latex(): Export from raw LaTeX
  - export_mathml_from_ast(): Export from AST node

Upstream: Block (formula type), formula_ast.py

Downstream: Office interop, accessibility tools, W3C validation
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def export_mathml_from_block(block: dict[str, Any] | Any) -> str:
    """Export a formula Block to Presentation MathML.

    Reads the ``raw_content`` (LaTeX) from the block and converts it to MathML
    via the formula AST. Falls back to LaTeX source if AST parsing fails.

    Args:
        block: A formula Block object (with raw_content attribute) or dict.

    Returns:
        A complete Presentation MathML string, or the original LaTeX
        wrapped in <mtext> if conversion fails.
    """
    latex = _get_latex_from_block(block)
    if not latex:
        return ""

    return export_mathml_from_latex(latex)


def export_mathml_from_latex(latex: str) -> str:
    """Convert a LaTeX math string to Presentation MathML.

    Uses the formula AST parser for structural conversion, with fallback
    to text wrapping on parse error.

    Args:
        latex: LaTeX math mode string (e.g., ``\frac{a}{b}``).

    Returns:
        A complete Presentation MathML string.
    """
    try:
        from docmirror.core.ocr.formula_ast import LaTeXSymbolTree
        ast = LaTeXSymbolTree.parse(latex)
        if ast.children:
            return LaTeXSymbolTree.to_mathml(ast)
    except Exception as e:
        logger.debug(f"[MathML] AST conversion failed: {e}")

    # Fallback: wrap raw LaTeX in <mtext>
    return '<math xmlns="http://www.w3.org/1998/Math/MathML"><mrow><mtext>' + _escape_xml(latex) + '</mtext></mrow></math>'


def export_mathml_from_ast(ast: Any) -> str:
    """Export directly from an AST node to MathML.

    Args:
        ast: An ASTNode from formula_ast.py.

    Returns:
        A complete Presentation MathML string.
    """
    try:
        from docmirror.core.ocr.formula_ast import LaTeXSymbolTree
        return LaTeXSymbolTree.to_mathml(ast)
    except Exception as e:
        logger.debug(f"[MathML] AST serialisation failed: {e}")
        return ""


def _get_latex_from_block(block: Any) -> str:
    """Extract LaTeX string from a formula Block.

    Handles both Block objects (with raw_content attribute) and dicts.
    """
    if hasattr(block, "raw_content"):
        return str(block.raw_content or "")
    if isinstance(block, dict):
        return str(block.get("raw_content", block.get("text", "")))
    return ""


def _escape_xml(s: str) -> str:
    """Escape special XML characters."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;")
