# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Paragraph / Formula Continuation Resolver — detect cross-page paragraph and
formula continuations.

P0 deterministic signals:
  - no_terminal_punctuation: last paragraph on page lacks sentence terminator
  - hyphen_or_dash_break: English hyphenation or Chinese dash break
  - style_match: font, size, indent, line spacing match
  - position_match: page-bottom + next-page-top in body region
  - section_continuity: same section
  - noise_excluded: header/footer excluded before checking

GA F8: Cross-page formula detection added with formula-specific signals:
  - formula_position_match: last formula on page n, first on page n+1
  - formula_latex_continuity: no balanced braces or missing closing structure
"""

from __future__ import annotations

from typing import Any

TERMINAL_PUNCTUATION = {".", "。", "?", "？", "!", "！", ":", "：", ")", "）", '"', '"', "”", "」"}


def detect_continuations(
    nodes: list[dict[str, Any]],
    *,
    confidence_threshold: float = 0.6,
) -> list[dict[str, Any]]:
    """Detect cross-page paragraph and formula continuations.

    Args:
        nodes: DFG StructureNode dicts sorted by reading_order.
        confidence_threshold: Minimum confidence to auto-merge (below = candidate only).

    Returns:
        List of cross_page_paragraph and cross_page_formula flow dicts.
    """
    flows: list[dict[str, Any]] = []

    # ── Paragraph continuations ────────────────────────────────────────
    paragraphs = [n for n in nodes if n.get("type") == "paragraph"]
    if len(paragraphs) >= 2:
        for i in range(len(paragraphs) - 1):
            curr = paragraphs[i]
            nxt = paragraphs[i + 1]

            curr_page = curr.get("page", 1)
            nxt_page = nxt.get("page", 1)
            if curr_page == nxt_page:
                continue

            signals = _evaluate_continuation_signals(curr, nxt)
            confidence = _compute_confidence(signals)

            if confidence >= confidence_threshold:
                flows.append(
                    {
                        "flow_id": f"flow:paragraph:p{curr_page}_p{nxt_page}_{i}",
                        "type": "cross_page_paragraph",
                        "node_ids": [curr.get("node_id", ""), nxt.get("node_id", "")],
                        "source_pages": [curr_page, nxt_page],
                        "confidence": round(confidence, 3),
                        "policy": "punctuation_style_position_v1",
                        "merged_view": (curr.get("text", "") + " " + nxt.get("text", "")).strip(),
                        "evidence_refs": [
                            curr.get("node_id", ""),
                            nxt.get("node_id", ""),
                        ],
                    }
                )

    # ── GA F8: Formula cross-page continuations ────────────────────────
    formulas = [n for n in nodes if n.get("type") == "formula"]
    if len(formulas) >= 2:
        for i in range(len(formulas) - 1):
            curr = formulas[i]
            nxt = formulas[i + 1]

            curr_page = curr.get("page", 1)
            nxt_page = nxt.get("page", 1)
            if curr_page == nxt_page:
                continue

            # Only consider consecutive pages
            if abs(nxt_page - curr_page) != 1:
                continue

            signals = _evaluate_formula_continuation_signals(curr, nxt, nodes)
            confidence = _compute_formula_confidence(signals)

            if confidence >= confidence_threshold:
                flows.append(
                    {
                        "flow_id": f"flow:formula:p{curr_page}_p{nxt_page}_{i}",
                        "type": "cross_page_formula",
                        "node_ids": [curr.get("node_id", ""), nxt.get("node_id", "")],
                        "source_pages": [curr_page, nxt_page],
                        "confidence": round(confidence, 3),
                        "policy": "formula_position_latex_v1",
                        "merged_view": (curr.get("text", "") + "\n" + nxt.get("text", "")).strip(),
                        "evidence_refs": [
                            curr.get("node_id", ""),
                            nxt.get("node_id", ""),
                        ],
                    }
                )

    return flows


# ═══════════════════════════════════════════════════════════════════════════════
# Paragraph continuation signals
# ═══════════════════════════════════════════════════════════════════════════════


def _evaluate_continuation_signals(
    curr: dict[str, Any],
    nxt: dict[str, Any],
) -> dict[str, bool | float]:
    """Evaluate continuation signals between two paragraph nodes."""
    signals: dict[str, bool | float] = {}

    curr_text = str(curr.get("text") or "").strip()
    # 1. No terminal punctuation on current paragraph
    if curr_text:
        last_char = curr_text[-1]
        signals["no_terminal_punctuation"] = last_char not in TERMINAL_PUNCTUATION
    else:
        signals["no_terminal_punctuation"] = False

    # 2. Hyphen or dash break
    if curr_text:
        signals["hyphen_or_dash_break"] = curr_text.endswith("-") or curr_text.endswith("—")
    else:
        signals["hyphen_or_dash_break"] = False

    # 3. Style match (bbox proximity as crude proxy for font/size)
    curr_bbox = curr.get("bbox")
    nxt_bbox = nxt.get("bbox")
    if curr_bbox and nxt_bbox and len(curr_bbox) >= 4 and len(nxt_bbox) >= 4:
        curr_height = float(curr_bbox[3]) - float(curr_bbox[1])
        nxt_height = float(nxt_bbox[3]) - float(nxt_bbox[1])
        height_ratio = (
            min(curr_height, nxt_height) / max(curr_height, nxt_height) if max(curr_height, nxt_height) > 0 else 1.0
        )
        signals["style_match"] = height_ratio > 0.7
    else:
        signals["style_match"] = False

    # 4. Position match: current near page bottom, next near page top
    if curr_bbox and nxt_bbox and len(curr_bbox) >= 4 and len(nxt_bbox) >= 2:
        curr_bottom = float(curr_bbox[3])
        nxt_top = float(nxt_bbox[1])
        signals["position_match"] = curr_bottom > 500 and nxt_top < 200
    else:
        signals["position_match"] = False

    # 5. Section continuity
    curr_section = str(curr.get("metadata", {}).get("section_id") or "")
    nxt_section = str(nxt.get("metadata", {}).get("section_id") or "")
    signals["section_continuity"] = (curr_section == nxt_section) if curr_section else False

    # 6. Noise excluded
    signals["noise_excluded"] = True

    return signals


def _compute_confidence(signals: dict[str, bool | float]) -> float:
    """Compute continuation confidence from signal scores."""
    weights = {
        "no_terminal_punctuation": 0.30,
        "position_match": 0.25,
        "style_match": 0.20,
        "section_continuity": 0.15,
        "hyphen_or_dash_break": 0.10,
    }
    score = 0.0
    for signal, weight in weights.items():
        if signals.get(signal):
            score += weight
    return min(1.0, score)


# ═══════════════════════════════════════════════════════════════════════════════
# GA F8: Formula cross-page continuation signals
# ═══════════════════════════════════════════════════════════════════════════════


def _evaluate_formula_continuation_signals(
    curr: dict[str, Any],
    nxt: dict[str, Any],
    all_nodes: list[dict[str, Any]],
) -> dict[str, bool | float]:
    """Evaluate cross-page formula continuation signals.

    Signals:
        - formula_position_match: current formula is last on page, next is first
        - latex_continuity: LaTeX has missing closing structure (no balanced braces)
        - same_display_type: both formulas have the same display type (inline/display)
        - noise_excluded: not header/footer formula
    """
    signals: dict[str, bool | float] = {}

    curr_page = curr.get("page", 1)
    nxt_page = nxt.get("page", 1)

    curr_text = str(curr.get("text") or "").strip()
    nxt_text = str(nxt.get("text") or "").strip()

    # 1. Formula position match: current is last formula on page, next is first
    same_page_nodes = [n for n in all_nodes if n.get("page") == curr_page]
    formulas_on_page = [n for n in same_page_nodes if n.get("type") == "formula"]
    curr_is_last = (formulas_on_page[-1].get("node_id") == curr.get("node_id")) if formulas_on_page else False

    nxt_page_nodes = [n for n in all_nodes if n.get("page") == nxt_page]
    formulas_on_nxt = [n for n in nxt_page_nodes if n.get("type") == "formula"]
    nxt_is_first = (formulas_on_nxt[0].get("node_id") == nxt.get("node_id")) if formulas_on_nxt else False

    signals["formula_position_match"] = curr_is_last and nxt_is_first

    # 2. LaTeX continuity: unbalanced braces in the first (suggesting it was split)
    curr_brace_count = curr_text.count("{") - curr_text.count("}")
    nxt_brace_count = nxt_text.count("{") - nxt_text.count("}")
    signals["latex_continuity"] = (
        curr_brace_count > 0  # current has unclosed braces
        or nxt_brace_count < 0  # next has unbalanced close braces (opened on prev page)
    )

    # 3. Same display type
    signals["same_display_type"] = curr.get("metadata", {}).get("formula_display_type") == nxt.get("metadata", {}).get(
        "formula_display_type"
    )

    # 4. Noise excluded
    signals["noise_excluded"] = True

    return signals


def _compute_formula_confidence(signals: dict[str, bool | float]) -> float:
    """Compute formula continuation confidence from signal scores."""
    weights = {
        "formula_position_match": 0.35,
        "latex_continuity": 0.35,
        "same_display_type": 0.20,
        "noise_excluded": 0.10,
    }
    score = 0.0
    for signal, weight in weights.items():
        if signals.get(signal):
            score += weight
    return min(1.0, score)


__all__ = [
    "detect_continuations",
]
