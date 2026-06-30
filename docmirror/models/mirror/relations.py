# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""RelationResolver — detect caption_of, title_of, footnote_of, references,
and formula_number_of relations.

P0 relations:
  - caption_of: nearby text below/above image matching figure/table patterns
  - title_of: table title above table matching table/Figure patterns
  - footnote_of: small text near page bottom or table/image boundary
  - references: body text referencing "见图 X / 表 Y / Eq. Z"
  - formula_number_of: body text referencing "式(5)" / "Equation (3)"

GA F9: formula_number_of edges added with explicit pattern matching and
formula number extraction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

FIGURE_PATTERNS = [
    re.compile(r"图\s*\d+", re.IGNORECASE),
    re.compile(r"fig(?:ure)?\s*\d+", re.IGNORECASE),
    re.compile(r"图片\s*\d+", re.IGNORECASE),
]

TABLE_PATTERNS = [
    re.compile(r"表\s*\d+", re.IGNORECASE),
    re.compile(r"table\s*\d+", re.IGNORECASE),
]

FORMULA_PATTERNS = [
    re.compile(r"公式\s*\d+", re.IGNORECASE),
    re.compile(r"eq(?:uation)?\s*\d+", re.IGNORECASE),
    re.compile(r"式\s*\d+", re.IGNORECASE),
    re.compile(r"\(\s*\d+(?:\.\d+)?\s*\)", re.IGNORECASE),
    re.compile(r"（\s*\d+(?:\.\d+)?\s*）", re.IGNORECASE),
]

# GA F9: Extract formula number from explicit references
_FORMULA_NUM_DIGIT = re.compile(
    r"(?:公式|式|Eq(?:uation)?\.?|eq(?:uation)?\.?)?\s*[\(（]?\s*(\d+(?:\.\d+)?)\s*[\)）]?",
    re.IGNORECASE,
)


@dataclass
class FormulaRefEvidence:
    """Evidence extracted from a formula reference in text."""

    pattern: str = ""
    confidence: float = 0.0


def resolve_relations(
    nodes: list[dict[str, Any]],
    *,
    profile: str = "ga_full",
) -> list[dict[str, Any]]:
    """Resolve semantic relations between structure nodes.

    Args:
        nodes: DFG StructureNode dicts sorted by reading_order.
        profile: Feature profile.

    Returns:
        List of relation dicts.
    """
    relations: list[dict[str, Any]] = []

    # Group nodes by type
    images = [n for n in nodes if n.get("type") == "image"]
    tables = [n for n in nodes if n.get("type") in ("physical_table", "logical_table")]
    formulas = [n for n in nodes if n.get("type") == "formula"]
    texts = [n for n in nodes if n.get("type") in ("paragraph", "heading")]

    # 1. Caption_of: text near image
    for img in images:
        img_page = img.get("page", 1)
        img_ro = img.get("reading_order", 0)

        nearby_texts = [t for t in texts if t.get("page") == img_page and abs(t.get("reading_order", 0) - img_ro) <= 3]

        for nt in nearby_texts:
            nt_text = str(nt.get("text") or "")
            if _matches_any_pattern(nt_text, FIGURE_PATTERNS):
                relations.append(
                    {
                        "relation_id": f"rel:caption:{nt.get('node_id', '')}:{img.get('node_id', '')}",
                        "type": "caption_of",
                        "from_node": nt.get("node_id", ""),
                        "to_node": img.get("node_id", ""),
                        "confidence": 0.85,
                        "policy": "nearby_text_pattern_v1",
                        "evidence_refs": [nt.get("node_id", ""), img.get("node_id", "")],
                    }
                )
                break

    # 2. Title_of: heading-like text near table
    for tbl in tables:
        tbl_page = tbl.get("page", 1)
        tbl_ro = tbl.get("reading_order", 0)

        nearby_texts = [t for t in texts if t.get("page") == tbl_page and abs(t.get("reading_order", 0) - tbl_ro) <= 2]

        for nt in nearby_texts:
            nt_text = str(nt.get("text") or "")
            if _matches_any_pattern(nt_text, TABLE_PATTERNS):
                relations.append(
                    {
                        "relation_id": f"rel:title:{nt.get('node_id', '')}:{tbl.get('node_id', '')}",
                        "type": "title_of",
                        "from_node": nt.get("node_id", ""),
                        "to_node": tbl.get("node_id", ""),
                        "confidence": 0.85,
                        "policy": "nearby_text_pattern_v1",
                        "evidence_refs": [nt.get("node_id", ""), tbl.get("node_id", "")],
                    }
                )
                break

    # ── 3. GA F9: Formula references with explicit numbering ──────────────
    # Assign formula numbers by page-order index if not already numbered
    _assign_default_formula_numbers(formulas, nodes)

    for fm in formulas:
        fm_page = fm.get("page", 1)
        fm_ro = fm.get("reading_order", 0)

        nearby_texts = [t for t in texts if t.get("page") == fm_page and abs(t.get("reading_order", 0) - fm_ro) <= 3]

        for nt in nearby_texts:
            nt_text = str(nt.get("text") or "")
            # First try explicit formula number reference
            match = _find_formula_number(nt_text)
            if match:
                formula_num = match.group(1)
                target = _find_formula_by_number(formulas, formula_num, fm_page)
                if target is not None:
                    evidence = _extract_formula_evidence(nt_text, formula_num)
                    relations.append(
                        {
                            "relation_id": f"rel:formula_number_of:{nt.get('node_id', '')}:{target.get('node_id', '')}",
                            "type": "formula_number_of",
                            "from_node": nt.get("node_id", ""),
                            "to_node": target.get("node_id", ""),
                            "confidence": evidence.confidence,
                            "policy": "formula_number_pattern_v1",
                            "evidence_refs": [nt.get("node_id", ""), target.get("node_id", "")],
                            "metadata": {
                                "pattern": evidence.pattern,
                                "formula_number": formula_num,
                            },
                        }
                    )
                    break
            # Fallback: generic formula reference pattern
            elif _matches_any_pattern(nt_text, FORMULA_PATTERNS):
                relations.append(
                    {
                        "relation_id": f"rel:formula_ref:{nt.get('node_id', '')}:{fm.get('node_id', '')}",
                        "type": "references",
                        "from_node": nt.get("node_id", ""),
                        "to_node": fm.get("node_id", ""),
                        "confidence": 0.70,
                        "policy": "nearby_text_pattern_v1",
                        "evidence_refs": [nt.get("node_id", ""), fm.get("node_id", "")],
                    }
                )
                break

    return relations


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _matches_any_pattern(text: str, patterns: list[re.Pattern]) -> bool:
    """Check if text matches any of the given regex patterns."""
    for pat in patterns:
        if pat.search(text):
            return True
    return False


def _find_formula_number(text: str) -> re.Match | None:
    """Find a formula number reference in text like 'Eq. (5)' or 'Equation 3.2'."""
    return _FORMULA_NUM_DIGIT.search(text)


def _extract_formula_evidence(text: str, formula_num: str) -> FormulaRefEvidence:
    """Extract evidence from a formula reference match.

    Higher confidence for explicit numbering patterns, lower for generic ones.
    """
    # Explicit: "Eq. (5)" or "Equation (5)"
    explicit = re.search(
        rf"(?:公式|式|Equation|Eq\.)\s*[\(（]\s*{re.escape(formula_num)}\s*[\)）]",
        text,
        re.IGNORECASE,
    )
    if explicit:
        return FormulaRefEvidence(pattern="explicit_paren", confidence=0.90)

    # Partial: "Eq. 5" or "Eq 5"
    partial = re.search(
        rf"(?:公式|式|Equation|Eq\.?)\s*{re.escape(formula_num)}",
        text,
        re.IGNORECASE,
    )
    if partial:
        return FormulaRefEvidence(pattern="explicit_no_paren", confidence=0.80)

    return FormulaRefEvidence(pattern="generic_digit", confidence=0.60)


def _find_formula_by_number(
    formulas: list[dict[str, Any]],
    formula_num: str,
    page: int,
) -> dict[str, Any] | None:
    """Find a formula node by its explicit formula_number or by page-order index.

    Priority:
        1. Exact match on metadata.formula_number
        2. Fallback: formula on same page at the numeric position (e.g., 5th formula)
    """
    # 1. Exact metadata match
    for fm in formulas:
        meta = fm.get("metadata", {})
        if str(meta.get("formula_number", "")) == formula_num:
            return fm

    # 2. Fallback: the nth formula on the given page
    page_formulas = [f for f in formulas if f.get("page") == page]
    try:
        idx = int(formula_num) - 1  # 1-based → 0-based
        if 0 <= idx < len(page_formulas):
            return page_formulas[idx]
    except (ValueError, TypeError):
        pass

    return None


def _assign_default_formula_numbers(
    formulas: list[dict[str, Any]],
    all_nodes: list[dict[str, Any]],
) -> None:
    """Assign default formula numbers by page-order.

    Formulas are numbered 1, 2, 3, ... within each page.
    This is stored in node metadata for reference resolution.
    """
    for page in sorted(set(fm.get("page", 1) for fm in formulas)):
        page_formulas = sorted(
            [f for f in formulas if f.get("page") == page],
            key=lambda f: f.get("reading_order", 0),
        )
        for i, fm in enumerate(page_formulas, start=1):
            meta = fm.get("metadata", {})
            if "formula_number" not in meta:
                meta["formula_number"] = str(i)
                fm["metadata"] = meta


__all__ = [
    "resolve_relations",
    "FormulaRefEvidence",
]
