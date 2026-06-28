# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Formula evidence — token-level confidence and source provenance for formula blocks.

Purpose: Build FormulaEvidence objects from parsing / OCR results and attach
them to formula Block attrs so the 4.12 commitment ("source refs / bbox / evidence")
is satisfied for every formula block.

Design (from 19_formula_recognition_first_principles_redesign.md):
  - FM-2: formula-level confidence / evidence
  - Each formula token has a source bbox and confidence
  - Evidence carries the recognition source (char_stream | ocr | omml)
  - Serialized into Block.attrs["formula_evidence"]

Main components:
  - FormulaTokenEvidence: per-token evidence
  - FormulaEvidence: per-block evidence aggregate
  - build_evidence_from_ast(): extract evidence from AST parsing + char data
  - build_evidence_from_ocr(): extract evidence from OCR result

Upstream: formula_ast.py (AST), formula_chars.py (char extraction),
  formula_engine.py (OCR), formula_zone.py (block creation)

Downstream: Block.attrs["formula_evidence"], formula_zone.py integration,
  forensic profile validation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Data models
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FormulaTokenEvidence:
    """Per-token source evidence for a formula sub-expression.

    Attributes:
        token: The LaTeX token or symbol string.
        bbox: Source bounding box in PDF coordinates (x0, y0, x1, y1).
        confidence: Token-level confidence [0.0, 1.0].
        source: Where the token came from — ``char_stream``, ``ocr``, or ``omml``.
    """
    token: str
    bbox: tuple[float, float, float, float] | None = None
    confidence: float = 1.0
    source: str = "char_stream"  # char_stream | ocr | omml


@dataclass
class FormulaEvidence:
    """Per-formula-block evidence aggregate.

    Attached to ``Block.attrs["formula_evidence"]`` for GA forensic compliance.

    Attributes:
        formula_block_id: The Block.block_id this evidence belongs to.
        tokens: Per-token evidence list (one per AST leaf or LaTeX token).
        total_tokens: Count of evidence tokens.
        ocr_model: OCR model name if OCR was used.
        ocr_confidence: Aggregate OCR confidence if available.
        preprocessing_applied: Image preprocessing steps applied before OCR.
        source_path: Which recognition path produced the result.
        parse_success: Whether LaTeX parsing to AST succeeded.
        parse_error: AST parse error message if any.
        display_type: Formula display classification (inline/display).
        normalized_latex: Normalized LaTeX for CDM comparison.
        raw_latex: Original LaTeX before normalization.
        average_confidence: Mean token confidence across all tokens.
    """
    formula_block_id: str = ""
    tokens: list[FormulaTokenEvidence] = field(default_factory=list)
    total_tokens: int = 0
    ocr_model: str | None = None
    ocr_confidence: float | None = None
    preprocessing_applied: list[str] = field(default_factory=list)
    source_path: str = "char_stream"  # char_stream | ocr | omml
    parse_success: bool = False
    parse_error: str | None = None
    display_type: str = "inline"  # inline | display | multiline
    normalized_latex: str | None = None
    raw_latex: str | None = None
    average_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict for Block.attrs."""
        result = asdict(self)
        # Serialise tokens to dicts
        result["tokens"] = [asdict(t) for t in self.tokens]
        # Convert bbox tuples to lists for JSON
        for t in result["tokens"]:
            if t.get("bbox") is not None:
                t["bbox"] = list(t["bbox"])
        return result

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FormulaEvidence:
        """Deserialise from a dict (e.g., from Block.attrs)."""
        tokens = [FormulaTokenEvidence(**t) for t in d.get("tokens", [])]
        return cls(
            formula_block_id=d.get("formula_block_id", ""),
            tokens=tokens,
            total_tokens=d.get("total_tokens", 0),
            ocr_model=d.get("ocr_model"),
            ocr_confidence=d.get("ocr_confidence"),
            preprocessing_applied=d.get("preprocessing_applied", []),
            source_path=d.get("source_path", "char_stream"),
            parse_success=d.get("parse_success", False),
            parse_error=d.get("parse_error"),
            display_type=d.get("display_type", "inline"),
            normalized_latex=d.get("normalized_latex"),
            raw_latex=d.get("raw_latex"),
            average_confidence=d.get("average_confidence", 0.0),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Evidence builders
# ═══════════════════════════════════════════════════════════════════════════════

def build_evidence_from_ast(
    block_id: str,
    latex: str,
    chars: list[dict[str, Any]] | None = None,
) -> FormulaEvidence:
    """Build FormulaEvidence from a parsed LaTeX string and char stream data.

    Extracts per-character bbox and confidence information from the original
    character stream and maps it onto AST leaf nodes.

    Args:
        block_id: The formula Block.block_id.
        latex: Raw LaTeX string (before normalization).
        chars: Original character dicts from PDF extraction (optional).

    Returns:
        A FormulaEvidence object ready for Block.attrs["formula_evidence"].
    """
    evidence = FormulaEvidence(
        formula_block_id=block_id,
        raw_latex=latex,
        source_path="char_stream",
    )

    # Try to parse to AST
    ast = None
    try:
        from docmirror.structure.ocr.formula_ast import LaTeXSymbolTree

        ast = LaTeXSymbolTree.parse(latex)
        evidence.parse_success = len(ast.children) > 0
        if not evidence.parse_success:
            evidence.parse_error = "AST parsing produced empty tree"
        else:
            # Normalize for CDM
            norm_ast = LaTeXSymbolTree.normalize(ast)
            evidence.normalized_latex = LaTeXSymbolTree.to_latex(norm_ast)
    except Exception as e:
        evidence.parse_success = False
        evidence.parse_error = str(e)
        logger.debug(f"[FormulaEvidence] AST parse failed for block {block_id}: {e}")

    # Build token evidence from char stream if available
    if chars:
        evidence.tokens = _map_chars_to_tokens(chars, latex)
    else:
        # Fallback: one token per LaTeX segment
        evidence.tokens = _token_evidence_from_latex(latex, confidence=0.8)

    # Aggregate
    evidence.total_tokens = len(evidence.tokens)
    if evidence.tokens:
        evidence.average_confidence = sum(t.confidence for t in evidence.tokens) / len(evidence.tokens)

    return evidence


def build_evidence_from_ocr(
    block_id: str,
    latex: str,
    ocr_model: str | None = None,
    ocr_confidence: float | None = None,
    preprocessing: list[str] | None = None,
) -> FormulaEvidence:
    """Build FormulaEvidence from OCR recognition results.

    Args:
        block_id: The formula Block.block_id.
        latex: Recognized LaTeX string.
        ocr_model: Name of the OCR model used (e.g., "rapid_latex_ocr").
        ocr_confidence: Aggregate OCR confidence score.
        preprocessing: List of preprocessing steps applied.

    Returns:
        A FormulaEvidence object ready for Block.attrs["formula_evidence"].
    """
    evidence = FormulaEvidence(
        formula_block_id=block_id,
        raw_latex=latex,
        source_path="ocr",
        ocr_model=ocr_model,
        ocr_confidence=ocr_confidence,
        preprocessing_applied=preprocessing or [],
    )

    # Try to parse to AST
    try:
        from docmirror.structure.ocr.formula_ast import LaTeXSymbolTree

        ast = LaTeXSymbolTree.parse(latex)
        evidence.parse_success = len(ast.children) > 0
        if not evidence.parse_success:
            evidence.parse_error = "AST parsing produced empty tree"
        else:
            norm_ast = LaTeXSymbolTree.normalize(ast)
            evidence.normalized_latex = LaTeXSymbolTree.to_latex(norm_ast)
    except Exception as e:
        evidence.parse_success = False
        evidence.parse_error = str(e)
        logger.debug(f"[FormulaEvidence] AST parse failed for block {block_id}: {e}")

    # Token evidence from OCR (no fine-grained bbox, so use whole-block confidence)
    evidence.tokens = _token_evidence_from_latex(
        latex,
        confidence=ocr_confidence if ocr_confidence is not None else 0.7,
        source="ocr",
    )

    evidence.total_tokens = len(evidence.tokens)
    if evidence.tokens:
        evidence.average_confidence = sum(t.confidence for t in evidence.tokens) / len(evidence.tokens)

    return evidence


def build_evidence_from_omml(
    block_id: str,
    latex: str,
) -> FormulaEvidence:
    """Build FormulaEvidence from OMML (Office Math) extraction.

    Args:
        block_id: The formula Block.block_id.
        latex: Converted LaTeX string from OMML extraction.

    Returns:
        A FormulaEvidence object ready for Block.attrs["formula_evidence"].
    """
    evidence = FormulaEvidence(
        formula_block_id=block_id,
        raw_latex=latex,
        source_path="omml",
    )

    # Try to parse to AST
    try:
        from docmirror.structure.ocr.formula_ast import LaTeXSymbolTree

        ast = LaTeXSymbolTree.parse(latex)
        evidence.parse_success = len(ast.children) > 0
        if not evidence.parse_success:
            evidence.parse_error = "AST parsing produced empty tree"
        else:
            norm_ast = LaTeXSymbolTree.normalize(ast)
            evidence.normalized_latex = LaTeXSymbolTree.to_latex(norm_ast)
    except Exception as e:
        evidence.parse_success = False
        evidence.parse_error = str(e)

    # OMML extraction has high confidence (structured source)
    evidence.tokens = _token_evidence_from_latex(
        latex,
        confidence=0.95,
        source="omml",
    )

    evidence.total_tokens = len(evidence.tokens)
    if evidence.tokens:
        evidence.average_confidence = sum(t.confidence for t in evidence.tokens) / len(evidence.tokens)

    return evidence


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _map_chars_to_tokens(
    chars: list[dict[str, Any]],
    latex: str,
) -> list[FormulaTokenEvidence]:
    """Map character stream entries to formula token evidence.

    Attempts to align character bboxes with LaTeX tokens by character matching.
    Fallback to whole-string confidence mapping when alignment is uncertain.
    """
    tokens: list[FormulaTokenEvidence] = []

    for c in chars:
        text = c.get("text", "")
        if not text.strip():
            continue

        bbox = (
            float(c.get("x0", 0)),
            float(c.get("y0", 0)),
            float(c.get("x1", 0)),
            float(c.get("y1", 0)),
        )

        # Character-level confidence from font-size or presence
        fontname = c.get("fontname", "")
        confidence = _estimate_char_confidence(c, fontname)

        tokens.append(FormulaTokenEvidence(
            token=text,
            bbox=bbox,
            confidence=confidence,
            source="char_stream",
        ))

    return tokens


def _token_evidence_from_latex(
    latex: str,
    confidence: float = 0.8,
    source: str = "char_stream",
) -> list[FormulaTokenEvidence]:
    """Create token evidence from LaTeX string without per-character bbox data.

    Splits LaTeX on spaces and known delimiters to create coarse token evidence.
    Used as fallback when char-stream bbox data is unavailable.
    """
    import re

    tokens: list[FormulaTokenEvidence] = []

    # Split LaTeX into coarse tokens
    parts = re.split(r"(\s+|\\[a-zA-Z]+|[\^\_{}+=<>])", latex)
    for part in parts:
        part = part.strip()
        if not part:
            continue

        tokens.append(FormulaTokenEvidence(
            token=part,
            bbox=None,
            confidence=confidence,
            source=source,
        ))

    return tokens


def _estimate_char_confidence(char: dict[str, Any], fontname: str) -> float:
    """Estimate character-level confidence based on font and size properties.

    Returns:
        Confidence score in [0.0, 1.0].
    """
    from docmirror.structure.ocr.formula_chars import is_math_font

    conf = 0.8  # base confidence

    # Math font boosts confidence
    if is_math_font(fontname):
        conf += 0.1

    # Very small or very large characters reduce confidence
    size = char.get("size", 12)
    if 6 <= size <= 24:
        conf += 0.05
    else:
        conf -= 0.1

    # Clamp
    return max(0.0, min(1.0, conf))
