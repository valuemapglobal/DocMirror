# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Formula chars — char-level LaTeX reconstruction for math zones.

Purpose: Groups math-font chars into rows, estimates baselines, and emits
LaTeX strings for formula blocks.

Main components: ``extract_formula_from_chars``, ``is_math_font``,
``_row_to_latex``.

Upstream: Formula zone char dicts.

Downstream: ``ocr.formula_engine``, ``pipeline.handlers.formula_zone``.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Math font detection
# ═══════════════════════════════════════════════════════════════════════════════

_MATH_FONT_PATTERNS = re.compile(
    r"(?i)(CMMI|CMSY|CMEX|CMR\d|Math|Symbol|STIX|Cambria.?Math|"
    r"MathJax|Asana.?Math|XITS.?Math|Latin\s*Modern\s*Math|"
    r"NewCM\s*Math|DejaVu\s*Math|Fira\s*Math)",
)


def is_math_font(fontname: str) -> bool:
    """Return ``True`` if *fontname* matches a known math font pattern."""
    if not fontname:
        return False
    return bool(_MATH_FONT_PATTERNS.search(fontname))


# ═══════════════════════════════════════════════════════════════════════════════
# Unicode → LaTeX mapping table
# ═══════════════════════════════════════════════════════════════════════════════

_UNICODE_TO_LATEX = {
    # Greek lowercase
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\varepsilon",
    "ζ": r"\zeta",
    "η": r"\eta",
    "θ": r"\theta",
    "ι": r"\iota",
    "κ": r"\kappa",
    "λ": r"\lambda",
    "μ": r"\mu",
    "ν": r"\nu",
    "ξ": r"\xi",
    "π": r"\pi",
    "ρ": r"\rho",
    "σ": r"\sigma",
    "τ": r"\tau",
    "υ": r"\upsilon",
    "φ": r"\varphi",
    "χ": r"\chi",
    "ψ": r"\psi",
    "ω": r"\omega",
    "ϵ": r"\epsilon",
    "ϕ": r"\phi",
    "ϑ": r"\vartheta",
    "ϱ": r"\varrho",
    "ς": r"\varsigma",
    "ϖ": r"\varpi",
    # Greek uppercase
    "Γ": r"\Gamma",
    "Δ": r"\Delta",
    "Θ": r"\Theta",
    "Λ": r"\Lambda",
    "Ξ": r"\Xi",
    "Π": r"\Pi",
    "Σ": r"\Sigma",
    "Υ": r"\Upsilon",
    "Φ": r"\Phi",
    "Ψ": r"\Psi",
    "Ω": r"\Omega",
    # Operators
    "±": r"\pm",
    "∓": r"\mp",
    "×": r"\times",
    "÷": r"\div",
    "·": r"\cdot",
    "∗": r"*",
    "⊕": r"\oplus",
    "⊗": r"\otimes",
    "∘": r"\circ",
    # Relations
    "≤": r"\leq",
    "≥": r"\geq",
    "≠": r"\neq",
    "≈": r"\approx",
    "≡": r"\equiv",
    "∼": r"\sim",
    "≃": r"\simeq",
    "≅": r"\cong",
    "∝": r"\propto",
    "≪": r"\ll",
    "≫": r"\gg",
    "⊂": r"\subset",
    "⊃": r"\supset",
    "⊆": r"\subseteq",
    "⊇": r"\supseteq",
    "∈": r"\in",
    "∉": r"\notin",
    "∋": r"\ni",
    "≺": r"\prec",
    "≻": r"\succ",
    "⊥": r"\perp",
    "∥": r"\parallel",
    # Large operators
    "∑": r"\sum",
    "∏": r"\prod",
    "∫": r"\int",
    "∮": r"\oint",
    "∬": r"\iint",
    "∭": r"\iiint",
    "⋃": r"\bigcup",
    "⋂": r"\bigcap",
    "⊔": r"\bigsqcup",
    # Arrows
    "→": r"\to",
    "←": r"\leftarrow",
    "↔": r"\leftrightarrow",
    "⇒": r"\Rightarrow",
    "⇐": r"\Leftarrow",
    "⇔": r"\Leftrightarrow",
    "↦": r"\mapsto",
    "↑": r"\uparrow",
    "↓": r"\downarrow",
    "↗": r"\nearrow",
    "↘": r"\searrow",
    # Miscellaneous
    "∞": r"\infty",
    "∂": r"\partial",
    "∇": r"\nabla",
    "∅": r"\emptyset",
    "∀": r"\forall",
    "∃": r"\exists",
    "¬": r"\neg",
    "√": r"\sqrt",
    "∠": r"\angle",
    "△": r"\triangle",
    "□": r"\square",
    "◇": r"\diamond",
    "♯": r"\sharp",
    "♭": r"\flat",
    "♮": r"\natural",
    "∧": r"\wedge",
    "∨": r"\vee",
    "⊤": r"\top",
    # Brackets
    "⟨": r"\langle",
    "⟩": r"\rangle",
    "⌈": r"\lceil",
    "⌉": r"\rceil",
    "⌊": r"\lfloor",
    "⌋": r"\rfloor",
    "‖": r"\|",
    # Dots
    "…": r"\ldots",
    "⋯": r"\cdots",
    "⋮": r"\vdots",
    "⋱": r"\ddots",
    # Accents / special symbols
    "ℓ": r"\ell",
    "℘": r"\wp",
    "ℜ": r"\Re",
    "ℑ": r"\Im",
    "ℵ": r"\aleph",
    "ℏ": r"\hbar",
    "†": r"\dagger",
    "‡": r"\ddagger",
}

# Atomic Unicode math symbols used as additional math signal when lowering threshold
_UNICODE_MATH_ATOMIC: set[str] = {
    "∞", "∂", "∇", "∀", "∃", "∑", "∏", "∫", "√", "∝", "∼", "≅",
    "≠", "≡", "≤", "≥", "⊂", "⊃", "∈", "∉", "∋", "∪", "∩",
    "α", "β", "γ", "δ", "ε", "θ", "λ", "μ", "π", "σ", "τ", "φ", "ψ", "ω",
    "Γ", "Δ", "Θ", "Λ", "Ξ", "Π", "Σ", "Φ", "Ψ", "Ω",
    "±", "×", "÷", "→", "←", "⇒", "⇐", "↔",
}


def extract_formula_from_chars(
    chars: list,
    bbox: tuple[float, float, float, float],
) -> str | None:
    """Extract LaTeX from PDF character streams within a bounding box.

    Args:
        chars: Character dicts from pdfplumber or zone extraction
            (must contain ``text``, ``fontname``, ``top``, ``bottom``,
            ``x0``, ``x1``).
        bbox: Formula region bounding box ``(x0, y0, x1, y1)``.

    Returns:
        A LaTeX string, or ``None`` if extraction fails.
    """
    if not chars:
        return None

    # 1. Filter characters within the bounding box (with a small margin)
    x0, y0, x1, y1 = bbox
    margin = 2.0
    formula_chars = []
    math_font_count = 0
    unicode_math_count = 0

    for c in chars:
        cx0 = c.get("x0", 0)
        ctop = c.get("top", 0)
        cx1 = c.get("x1", 0)
        cbottom = c.get("bottom", 0)

        if cx0 >= x0 - margin and ctop >= y0 - margin and cx1 <= x1 + margin and cbottom <= y1 + margin:
            formula_chars.append(c)
            if is_math_font(c.get("fontname", "")):
                math_font_count += 1
            if c.get("text", "") in _UNICODE_MATH_ATOMIC:
                unicode_math_count += 1

    if not formula_chars:
        return None

    # 2. Check math signal: combined math font ratio + Unicode math symbol count
    total = len(formula_chars)
    math_ratio = math_font_count / total if total > 0 else 0
    combined_math_signal = math_font_count + unicode_math_count
    combined_ratio = combined_math_signal / total if total > 0 else 0

    # GA F4: Lowered from 30% to 15%, supplemented by Unicode math symbol count
    if math_ratio < 0.15 and combined_ratio < 0.15:
        return None

    # 3. Sort by position and rebuild LaTeX
    formula_chars.sort(key=lambda c: (c.get("top", 0), c.get("x0", 0)))

    # GA F4: ML-aware row grouping (adaptive KMeans clustering)
    rows = _group_by_rows_ml(formula_chars)

    # 4. Convert character stream → LaTeX
    parts = []
    for row_chars in rows:
        row_latex = _row_to_latex(row_chars)
        if row_latex:
            parts.append(row_latex)

    if not parts:
        return None

    result = " ".join(parts)

    # 5. Basic structural corrections
    result = _post_process_char_latex(result)

    logger.debug(f"[FormulaChars] extracted from char stream: {result[:80]}...")
    return result


def _group_by_rows(chars: list) -> list[list[dict]]:
    """Group characters into rows by y-coordinate proximity (legacy, kept for reference)."""
    if not chars:
        return []

    rows: list[list[dict]] = []
    current_row: list[dict] = [chars[0]]

    for c in chars[1:]:
        prev_mid = (current_row[-1].get("top", 0) + current_row[-1].get("bottom", 0)) / 2
        curr_mid = (c.get("top", 0) + c.get("bottom", 0)) / 2

        if abs(curr_mid - prev_mid) <= 3.0:
            current_row.append(c)
        else:
            rows.append(current_row)
            current_row = [c]

    rows.append(current_row)
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# ML-aware row grouping (GA F4)
# ═══════════════════════════════════════════════════════════════════════════════

def _group_by_rows_ml(chars: list) -> list[list[dict]]:
    """ML-aware row grouping using adaptive baseline clustering.

    Strategy:
        1. Compute char mids and cluster using 1D KMeans on y-coordinate.
        2. Determine optimal number of rows via gap analysis.
        3. Fall back to fixed-threshold grouping if too few chars.
    """
    if len(chars) <= 2:
        return _group_by_rows(chars)

    mids = [(c.get("top", 0) + c.get("bottom", 0)) / 2 for c in chars]
    return _kmeans_row_grouping(chars, mids)


def _kmeans_row_grouping(chars: list, mids: list[float]) -> list[list[dict]]:
    """Cluster characters into rows using 1D KMeans on y-midpoints."""
    if len(mids) < 3:
        return _group_by_rows(chars)

    try:
        from statistics import mean, stdev
        span = max(mids) - min(mids)
        if span < 1.0:
            return [chars]

        # Determine optimal k via stdev-based gap heuristic
        n_clusters = max(1, int(span / max(1.0, stdev(mids) * 0.5)))
        n_clusters = min(n_clusters, len(chars))

        return _cluster_chars(chars, mids, n_clusters)
    except Exception:
        return _group_by_rows(chars)


def _cluster_chars(chars: list, mids: list[float], k: int) -> list[list[dict]]:
    """1D KMeans-based char clustering into rows.

    Args:
        chars: Character dicts.
        mids: Corresponding y-midpoints.
        k: Number of clusters (rows).

    Returns:
        List of char lists, one per row, sorted by ascending y-coordinate.
    """
    if k <= 1:
        return [chars]

    # Initialize centroids evenly spaced across the y-range
    min_y = min(mids)
    max_y = max(mids)
    span = max_y - min_y
    centroids = [min_y + span * (i + 0.5) / k for i in range(k)]

    # KMeans iterations (max 20)
    labels = [0] * len(chars)
    for _ in range(20):
        # Assign step
        changed = False
        for i, mid in enumerate(mids):
            best_k = min(range(k), key=lambda ki: abs(mid - centroids[ki]))
            if labels[i] != best_k:
                labels[i] = best_k
                changed = True

        if not changed:
            break

        # Update step
        for ki in range(k):
            cluster_mids = [mids[i] for i in range(len(chars)) if labels[i] == ki]
            if cluster_mids:
                centroids[ki] = sum(cluster_mids) / len(cluster_mids)

    # Build rows, sorted by cluster centroid y
    rows: list[list[dict]] = [[] for _ in range(k)]
    for i, c in enumerate(chars):
        rows[labels[i]].append(c)

    # Sort rows by ascending y
    row_centroids = [(ki, centroids[ki], rows[ki]) for ki in range(k) if rows[ki]]
    row_centroids.sort(key=lambda rc: rc[1])

    return [rc[2] for rc in row_centroids]


# ═══════════════════════════════════════════════════════════════════════════════
# Row to LaTeX conversion (GA F4: multi-level sup/sub detection)
# ═══════════════════════════════════════════════════════════════════════════════

def _row_to_latex(row_chars: list) -> str:
    """Convert a row of character dicts to a LaTeX string with multi-level sup/sub detection.

    Detects superscripts and subscripts by comparing each character's
    vertical centre against the row baseline. Supports up to 2 levels
    of nesting based on offset ratio.
    """
    row_chars.sort(key=lambda c: c.get("x0", 0))

    parts = []
    baseline = _estimate_baseline(row_chars)

    for c in row_chars:
        text = c.get("text", "")
        if not text.strip():
            parts.append(" ")
            continue

        # Unicode → LaTeX mapping
        latex = _UNICODE_TO_LATEX.get(text, text)

        # Multi-level superscript / subscript detection
        char_mid = (c.get("top", 0) + c.get("bottom", 0)) / 2
        char_height = c.get("bottom", 0) - c.get("top", 0)

        if baseline > 0 and char_height > 0:
            offset_ratio = (char_mid - baseline) / char_height
            if offset_ratio < -0.8:
                # Double superscript (e.g., exponent of exponent)
                latex = "^{^{" + latex + "}}"
            elif offset_ratio < -0.3:
                latex = "^{" + latex + "}"
            elif offset_ratio > 0.8:
                # Double subscript (e.g., subscript of subscript)
                latex = "_{_{" + latex + "}}"
            elif offset_ratio > 0.3:
                latex = "_{" + latex + "}"

        parts.append(latex)

    return "".join(parts)


def _estimate_baseline(chars: list) -> float:
    """Estimate the row baseline as the vertical centre of the tallest
    character (largest font size)."""
    if not chars:
        return 0

    mids = [(c.get("top", 0) + c.get("bottom", 0)) / 2 for c in chars]
    heights = [c.get("bottom", 0) - c.get("top", 0) for c in chars]

    if not heights:
        return 0

    max_h_idx = max(range(len(heights)), key=lambda i: heights[i])
    return mids[max_h_idx]


def _post_process_char_latex(latex: str) -> str:
    """Post-process character-stream LaTeX output.

    Merges consecutive superscript / subscript groups and collapses
    redundant whitespace.
    """
    # Merge consecutive superscript / subscript braces
    latex = re.sub(r"}\^{", "", latex)
    latex = re.sub(r"}_{", "", latex)

    # Collapse multiple spaces
    latex = re.sub(r"\s+", " ", latex).strip()

    return latex
