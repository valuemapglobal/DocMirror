# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Zone builder — constructs typed zones from layout extents.

Purpose: Refines detected regions into ``Zone`` objects via line consensus,
formula isolation, and legacy y-band fallbacks.

Main components: ``_build_zones_from_extent``, ``_refine_by_lines``,
``_classify_zone_legacy``.

Upstream: ``segment.layout_analysis``, ``spatial_graph``, ``negative_space``.

Downstream: ``segment.zone_segment``, ``pipeline.stages.page_segment``.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict

from docmirror.layout.segment.zone_models import Zone
from docmirror.structure.utils.vocabulary import _ALL_BORDER_CHARS, HLINE_CHARS, KNOWN_HEADER_WORDS, PIPE_CHARS

logger = logging.getLogger(__name__)


def _isolate_formula_components(chars: list[dict], page_w: float, page_h: float) -> tuple[list[dict], list[Zone]]:
    """
    Isolates formula regions using Union-Find connected component clustering
    of character bounding boxes. No cv2/numpy dependency required.

    Algorithm:
      1. Identify math seed characters (extreme aspect ratio or Unicode math symbols).
      2. Build dilated AABBs: seeds get +15pt horizontal, +8pt vertical expansion;
         all chars get a morphological close equivalent (+7.5pt H, +2.5pt V).
      3. Sort by Y, sweep-line merge overlapping AABBs via Union-Find.
      4. Connected components containing ≥1 math seed and <150 chars → formula zones.

    Returns: (remaining_chars, formula_zones)
    """
    if not chars or page_w <= 0 or page_h <= 0:
        return chars, []

    MATH_UNICODE = set("∑∫∏√∞∂∇±×÷≈≡≠≤≥⊂⊃⊆⊇∈∉∪∩")

    # ── Step 1: Identify math seed indices ──
    math_seed_set = set()
    for i, c in enumerate(chars):
        h = c.get("bottom", 0) - c.get("top", 0)
        w = c.get("x1", 0) - c.get("x0", 0)
        text = c.get("text", "").strip()

        if h > 0 and w > 0:
            aspect = h / w
            if aspect > 2.5 or aspect < 0.2:
                math_seed_set.add(i)
            elif text and text[0] in MATH_UNICODE:
                math_seed_set.add(i)

    if not math_seed_set:
        return chars, []

    # ── Step 2: Build dilated AABBs ──
    # Morph-close equivalent: expand every char slightly so adjacent
    # chars in the same formula merge; seeds get extra dilation.
    SEED_EXPAND_X, SEED_EXPAND_Y = 15.0, 8.0
    CLOSE_EXPAND_X, CLOSE_EXPAND_Y = 7.5, 2.5

    aabbs = []  # (x0, y0, x1, y1) per char — dilated
    for i, c in enumerate(chars):
        cx0, cy0 = c.get("x0", 0), c.get("top", 0)
        cx1, cy1 = c.get("x1", 0), c.get("bottom", 0)
        if i in math_seed_set:
            aabbs.append(
                (
                    cx0 - SEED_EXPAND_X,
                    cy0 - SEED_EXPAND_Y,
                    cx1 + SEED_EXPAND_X,
                    cy1 + SEED_EXPAND_Y,
                )
            )
        else:
            aabbs.append(
                (
                    cx0 - CLOSE_EXPAND_X,
                    cy0 - CLOSE_EXPAND_Y,
                    cx1 + CLOSE_EXPAND_X,
                    cy1 + CLOSE_EXPAND_Y,
                )
            )

    # ── Step 3: Union-Find with sweep-line AABB overlap ──
    n = len(chars)
    parent = list(range(n))
    rank = [0] * n

    def _find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    def _union(a, b):
        ra, rb = _find(a), _find(b)
        if ra == rb:
            return
        if rank[ra] < rank[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank[ra] == rank[rb]:
            rank[ra] += 1

    # Sort char indices by dilated y0 for sweep-line
    sorted_indices = sorted(range(n), key=lambda i: aabbs[i][1])

    # Sweep-line: for each char, check overlap with active chars
    # Active set: chars whose dilated y1 >= current char's dilated y0
    # Use a simple list scan (chars per page typically < 3000, fast enough)
    active = []  # list of indices currently in the sweep window
    for idx in sorted_indices:
        ax0, ay0, ax1, ay1 = aabbs[idx]

        # Prune expired active entries
        active = [j for j in active if aabbs[j][3] >= ay0]

        # Check overlap with each active entry
        for j in active:
            bx0, by0, bx1, by1 = aabbs[j]
            # AABB overlap test (Y already guaranteed by sweep)
            if ax0 <= bx1 and ax1 >= bx0:
                _union(idx, j)

        active.append(idx)

    # ── Step 4: Extract connected components with math seeds ──
    components: dict[int, list] = defaultdict(list)
    for i in range(n):
        components[_find(i)].append(i)

    formula_zones = []
    used_char_indices = set()

    for root, member_indices in components.items():
        # Must contain at least one math seed
        math_count = sum(1 for i in member_indices if i in math_seed_set)
        if math_count == 0:
            continue

        # Skip massive text blocks (> 150 chars → not a formula)
        if len(member_indices) >= 150:
            continue

        # Skip components spanning > 90% page width or > 50% page height
        comp_chars = [chars[i] for i in member_indices]
        fx0 = min(c["x0"] for c in comp_chars)
        fy0 = min(c["top"] for c in comp_chars)
        fx1 = max(c["x1"] for c in comp_chars)
        fy1 = max(c["bottom"] for c in comp_chars)

        if (fx1 - fx0) > page_w * 0.9 or (fy1 - fy0) > page_h * 0.5:
            continue

        used_char_indices.update(member_indices)
        ftext = "".join(c["text"] for c in sorted(comp_chars, key=lambda c: (c["top"], c["x0"])))
        formula_zones.append(
            Zone(
                type="formula",
                bbox=(fx0, fy0, fx1, fy1),
                chars=comp_chars,
                text=ftext.strip(),
                confidence=0.9,
            )
        )

    remaining_chars = [c for i, c in enumerate(chars) if i not in used_char_indices]
    return remaining_chars, formula_zones


def _column_consensus(
    chars: list[dict],
    page_w: float,
    page_h: float,
    min_cols: int = 3,
    min_rows: int = 3,
    cell_gap: float = 8.0,
    y_bin: float | None = None,
) -> tuple | None:
    """Column Consensus: detect table extent by structural repetition.

    Human visual pattern: a table is N rows where each row has M text
    segments at consistent X-positions.  Uses X-position clustering
    instead of quantization — no parameters to tune, no boundary effects.

    Algorithm:
      1. Group chars into rows by y_mid.
      2. Split each row into cells by x-gap.
      3. Collect ALL cell-start X positions → cluster by natural gaps.
      4. Map each row's cells to nearest column cluster.
      5. Rows with consistent column count → table rows.
      6. Return (table_y_top, table_y_bottom, column_x_positions).

    Returns:
        (y_top, y_bottom, [col_x_positions]) or None if no table found.
    """
    if not chars or page_w <= 0 or page_h <= 0:
        return None

    # ── Step 0: Bypass for explicitly bordered grid tables ──
    # Strongly bordered tables naturally compress whitespace within cells (e.g. 4pt gaps),
    # rendering spatial-gap clustering fundamentally unsuitable. If dense structural
    # borders are detected, immediately bypass spatial consensus.
    border_chars_count = sum(1 for c in chars if c.get("text", "") in _ALL_BORDER_CHARS)
    if border_chars_count > 30:
        return None  # Defer to grid-aware fallback (legacy Y-band)

    # ── Step 1: Group chars into rows by y_mid ──
    # y_bin default: 3pt (proven for standard 12pt fonts).
    # Adaptive mode passes median_height * 0.4 for abnormal font sizes.
    _y_bin = y_bin if y_bin is not None else 3.0
    y_groups: dict[int, list] = defaultdict(list)
    for c in chars:
        y_mid = (c.get("top", 0) + c.get("bottom", 0)) / 2
        y_key = round(y_mid / _y_bin) * _y_bin
        y_groups[y_key].append(c)

    # ── Step 2: Split each row into cells by x-gap ──
    # Adaptive cell_gap based on median character width
    char_widths = [c.get("x1", 0) - c.get("x0", 0) for c in chars if c.get("x1", 0) > c.get("x0", 0)]
    if char_widths:
        sorted_w = sorted(char_widths)
        median_w = sorted_w[len(sorted_w) // 2]
        cell_gap = max(cell_gap, median_w * 1.5)

    row_cell_starts: dict[int, list] = {}  # y_key → [raw x_start, ...]

    for y_key in sorted(y_groups.keys()):
        row_chars = sorted(y_groups[y_key], key=lambda c: c.get("x0", 0))
        if len(row_chars) < 2:
            continue

        cell_starts = [row_chars[0]["x0"]]
        for i in range(1, len(row_chars)):
            gap = row_chars[i]["x0"] - row_chars[i - 1].get("x1", row_chars[i - 1]["x0"])
            if gap > cell_gap:
                cell_starts.append(row_chars[i]["x0"])

        if len(cell_starts) >= min_cols:
            row_cell_starts[y_key] = cell_starts

    if not row_cell_starts:
        return None

    # ── Step 3: Cluster all cell-start X positions ──
    # Collect every cell-start X from every multi-cell row.
    all_x = []
    for starts in row_cell_starts.values():
        all_x.extend(starts)
    all_x.sort()

    if not all_x:
        return None

    # Gap-based clustering: sort X values, split where gap > threshold.
    # Threshold = median of all inter-X gaps × 3 (large gaps = column breaks).
    inter_gaps = [all_x[i + 1] - all_x[i] for i in range(len(all_x) - 1)]
    if not inter_gaps:
        return None

    sorted_gaps = sorted(inter_gaps)
    median_inter_gap = sorted_gaps[len(sorted_gaps) // 2]
    # Cluster split threshold: gaps significantly larger than typical
    # within-cluster variation are column boundaries.
    cluster_threshold = max(median_inter_gap * 3, 15.0)

    clusters: list[list] = [[all_x[0]]]
    for i in range(1, len(all_x)):
        if all_x[i] - all_x[i - 1] > cluster_threshold:
            clusters.append([all_x[i]])
        else:
            clusters[-1].append(all_x[i])

    if len(clusters) < min_cols:
        return None

    # Compute cluster centers (median of each cluster)
    col_centers = []
    for cl in clusters:
        cl.sort()
        col_centers.append(cl[len(cl) // 2])

    logger.debug(
        f"column_consensus: {len(clusters)} column clusters from "
        f"{len(all_x)} X-positions, threshold={cluster_threshold:.1f}"
    )

    # ── Step 4: Map each row's cells to column clusters ──
    def _map_to_cols(cell_starts: list) -> tuple:
        """Map cell starts to closest column clusters → column ID tuple."""
        col_ids = []
        for x in cell_starts:
            best_col = min(range(len(col_centers)), key=lambda i: abs(x - col_centers[i]))
            col_ids.append(best_col)
        return tuple(col_ids)

    row_col_ids: dict[int, tuple] = {}
    for y_key, starts in row_cell_starts.items():
        col_ids = _map_to_cols(starts)
        row_col_ids[y_key] = col_ids

    # ── Step 5: Find consensus — best signature ──
    # A "signature" is now the tuple of column IDs the row's cells belong to.
    sig_counter: dict[tuple, list] = defaultdict(list)
    for y_key, col_ids in row_col_ids.items():
        sig_counter[col_ids].append(y_key)

    def _count_absorbable(candidate_sig: tuple) -> int:
        """Count rows absorbable by this signature using subset logic."""
        cn = len(candidate_sig)
        cand_set = set(candidate_sig)
        total_rows = list(sig_counter[candidate_sig])
        for other_sig, other_rows in sig_counter.items():
            if other_sig == candidate_sig:
                continue
            on = len(other_sig)
            other_set = set(other_sig)

            # Fewer cols: subset wrap. Every col in other MUST be in candidate.
            if on < cn and on >= min_cols:
                if other_set.issubset(cand_set):
                    total_rows.extend(other_rows)
            # More cols (+2 allowance): candidate cols MUST be in other.
            elif on > cn and on <= cn + 2:
                if cand_set.issubset(other_set):
                    total_rows.extend(other_rows)
        return len(set(total_rows))

    # Best signature: most absorbable rows weighted by column count
    # Deterministic tie-breaker: (score, ncols, signature_tuple)
    best_sig = max(sig_counter.keys(), key=lambda s: (_count_absorbable(s) * len(s), len(s), s))
    best_rows = list(sig_counter[best_sig])
    best_ncols = len(best_sig)
    best_set = set(best_sig)

    # Absorb all valid subset/superset rows into the best table extent
    for sig, sig_rows in sig_counter.items():
        if sig == best_sig:
            continue
        ncols = len(sig)
        sig_set = set(sig)
        if ncols < best_ncols and ncols >= min_cols:
            if sig_set.issubset(best_set):
                best_rows.extend(sig_rows)
        elif ncols > best_ncols and ncols <= best_ncols + 2:
            if best_set.issubset(sig_set):
                best_rows.extend(sig_rows)

    best_rows = sorted(set(best_rows))

    if len(best_rows) < min_rows:
        return None

    # ── Step 6: Determine table extent ──
    table_y_top = best_rows[0]
    table_y_bottom = best_rows[-1]

    # Extend y_bottom to include the full height of the last row's chars
    last_row_chars = y_groups.get(best_rows[-1], [])
    if last_row_chars:
        table_y_bottom = max(c.get("bottom", table_y_bottom) for c in last_row_chars)

    # Gap-fill: include ALL y-groups between first and last matched row.
    # Multi-line continuation rows (wrapped company names) sit between
    # data rows and must be included in the table extent.
    all_ys = sorted(y_groups.keys())
    for yk in all_ys:
        if table_y_top <= yk <= best_rows[-1]:
            max_bottom = max(c.get("bottom", 0) for c in y_groups[yk])
            table_y_bottom = max(table_y_bottom, max_bottom)

    # Extend past the last matched row for trailing continuation rows
    last_idx = all_ys.index(best_rows[-1]) if best_rows[-1] in all_ys else -1
    if last_idx >= 0:
        for check_idx in range(last_idx + 1, min(last_idx + 4, len(all_ys))):
            next_y = all_ys[check_idx]
            if next_y not in row_cell_starts:
                gap = next_y - best_rows[-1]
                if gap < 30:
                    max_bottom = max(c.get("bottom", 0) for c in y_groups[next_y])
                    table_y_bottom = max(table_y_bottom, max_bottom)
                else:
                    break
            else:
                break

    # Include header row: the row immediately above table_top
    top_idx = all_ys.index(best_rows[0]) if best_rows[0] in all_ys else -1
    if top_idx > 0:
        candidate_y = all_ys[top_idx - 1]
        if candidate_y in row_cell_starts:
            cand_ncols = len(row_cell_starts[candidate_y])
            if abs(cand_ncols - best_ncols) <= 2:
                table_y_top = candidate_y
        elif candidate_y in y_groups:
            gap = best_rows[0] - candidate_y
            if gap < 30 and len(y_groups[candidate_y]) >= 3:
                table_y_top = candidate_y

    logger.debug(
        f"column_consensus: found table y={table_y_top:.0f}-{table_y_bottom:.0f} "
        f"cols={best_ncols} rows={len(best_rows)} "
        f"centers={[round(c) for c in col_centers]}"
    )

    return (table_y_top, table_y_bottom, [round(c) for c in col_centers])


def _refine_by_lines(
    table_extent: tuple,
    lines: list | None,
    rects: list | None = None,
) -> tuple:
    """Refine table extent using drawing lines (Tier 2).

    If horizontal lines exist near the table boundary, snap the boundary
    to the line position for pixel-perfect accuracy.
    """
    y_top, y_bottom, col_xs = table_extent
    if not lines and not rects:
        return table_extent

    all_lines = list(lines or [])

    # Extract horizontal line Y positions
    h_line_ys = []
    for ln in all_lines:
        ly0 = ln.get("top", ln.get("y0", 0))
        ly1 = ln.get("bottom", ln.get("y1", 0))
        lx0 = ln.get("x0", 0)
        lx1 = ln.get("x1", 0)
        # Horizontal line: height < 2pt, width > 50pt
        if abs(ly1 - ly0) < 2 and abs(lx1 - lx0) > 50:
            h_line_ys.append((ly0 + ly1) / 2)

    if not h_line_ys:
        return table_extent

    h_line_ys.sort()

    # Snap y_top to nearest h-line above (within 15pt)
    for ly in h_line_ys:
        if y_top - 15 <= ly <= y_top + 5:
            y_top = ly
            break

    # Snap y_bottom to nearest h-line below (within 15pt)
    for ly in reversed(h_line_ys):
        if y_bottom - 5 <= ly <= y_bottom + 15:
            y_bottom = ly
            break

    return (y_top, y_bottom, col_xs)


def _build_zones_from_extent(
    chars: list[dict],
    rects: list,
    table_extent: tuple,
    _page_w: float,
    _page_h: float,
    page_idx: int,
) -> list[Zone]:
    """Derive all zones from a precise table extent.

    Zones:
      - chars above table_top → title / summary
      - chars within table_top to table_bottom → data_table
      - chars below table_bottom → footer
    """
    y_top, y_bottom, col_xs = table_extent
    zones = []

    # Partition chars into above / table / below
    above_chars = [c for c in chars if c.get("bottom", 0) <= y_top + 3]
    table_chars = [c for c in chars if c.get("top", 0) >= y_top - 3 and c.get("bottom", 0) <= y_bottom + 3]
    below_chars = [c for c in chars if c.get("top", 0) >= y_bottom - 3]

    # Remove overlap: a char should be in exactly one group
    table_set = set(id(c) for c in table_chars)
    above_chars = [c for c in above_chars if id(c) not in table_set]
    below_chars = [c for c in below_chars if id(c) not in table_set]

    # ── Above table → title and/or summary ──
    if above_chars:
        # Split above chars into title (large/centered) and summary (has "：")
        # Group by y-bands first
        above_y_groups: dict[int, list] = defaultdict(list)
        for c in above_chars:
            yk = round(c["top"] / 3) * 3
            above_y_groups[yk].append(c)

        title_chars = []
        summary_chars = []
        for yk in sorted(above_y_groups.keys()):
            band = above_y_groups[yk]
            band_text = "".join(c["text"] for c in sorted(band, key=lambda c: c["x0"]))
            # title: no "：" and generally a heading
            if re.search(r"[\u4e00-\u9fff][：:]", band_text):
                summary_chars.extend(band)
            elif not title_chars and len(band_text.strip()) < 80:
                # First non-KV band is the title
                title_chars.extend(band)
            else:
                summary_chars.extend(band)

        if title_chars:
            x0 = min(c["x0"] for c in title_chars)
            x1 = max(c["x1"] for c in title_chars)
            y0 = min(c["top"] for c in title_chars)
            y1 = max(c["bottom"] for c in title_chars)
            text = "".join(c["text"] for c in sorted(title_chars, key=lambda c: (c["top"], c["x0"])))
            zones.append(
                Zone(
                    type="title",
                    bbox=(x0, y0, x1, y1),
                    page=page_idx,
                    chars=title_chars,
                    text=text.strip(),
                )
            )

        if summary_chars:
            x0 = min(c["x0"] for c in summary_chars)
            x1 = max(c["x1"] for c in summary_chars)
            y0 = min(c["top"] for c in summary_chars)
            y1 = max(c["bottom"] for c in summary_chars)
            text = "".join(c["text"] for c in sorted(summary_chars, key=lambda c: (c["top"], c["x0"])))
            zones.append(
                Zone(
                    type="summary",
                    bbox=(x0, y0, x1, y1),
                    page=page_idx,
                    chars=summary_chars,
                    text=text.strip(),
                )
            )

    # ── Table zone ──
    if table_chars:
        x0 = min(c["x0"] for c in table_chars)
        x1 = max(c["x1"] for c in table_chars)
        table_rects = [r for r in rects if r.get("top", 0) >= y_top - 3 and r.get("top", 0) <= y_bottom + 3]
        text = "".join(c["text"] for c in sorted(table_chars, key=lambda c: (c["top"], c["x0"])))
        zones.append(
            Zone(
                type="data_table",
                bbox=(x0, y_top, x1, y_bottom),
                page=page_idx,
                chars=table_chars,
                rects=table_rects,
                text=text.strip(),
            )
        )

    # ── Below table → footer ──
    if below_chars:
        x0 = min(c["x0"] for c in below_chars)
        x1 = max(c["x1"] for c in below_chars)
        y0 = min(c["top"] for c in below_chars)
        y1 = max(c["bottom"] for c in below_chars)
        text = "".join(c["text"] for c in sorted(below_chars, key=lambda c: (c["top"], c["x0"])))
        zones.append(
            Zone(
                type="footer",
                bbox=(x0, y0, x1, y1),
                page=page_idx,
                chars=below_chars,
                text=text.strip(),
            )
        )

    return zones


def _legacy_y_band_zones(
    chars: list[dict],
    rects: list,
    _page_w: float,
    page_h: float,
    page_idx: int,
    gap_threshold: float = 15.0,
) -> list[Zone]:
    """Legacy Y-band splitting fallback.

    Used when Column Consensus finds no table pattern.
    This is the original segment_page_into_zones logic preserved as fallback.
    """
    # Lazy load classify helper
    _PIPE_CHARS = PIPE_CHARS
    _KNOWN_HEADER_WORDS = KNOWN_HEADER_WORDS

    # Dynamic gap_threshold
    char_heights = [c["bottom"] - c["top"] for c in chars if c.get("bottom", 0) > c.get("top", 0)]
    if char_heights:
        sorted_h = sorted(char_heights)
        median_h = sorted_h[len(sorted_h) // 2]
        gap_threshold = max(12.0, median_h * 1.5)

    row_ys = sorted(set(round(c["top"] / 3) * 3 for c in chars))

    # Font-size change boundaries
    row_font_sizes: dict[int, float] = {}
    for y_key in row_ys:
        row_chars = [c for c in chars if round(c["top"] / 3) * 3 == y_key]
        sizes = [c.get("size", 0) for c in row_chars if c.get("size", 0) > 0]
        if sizes:
            sizes.sort()
            row_font_sizes[y_key] = sizes[len(sizes) // 2]

    # Pre-compute border character counts per y-key for structural cut detection
    _HLINE_CHARS = HLINE_CHARS

    row_border_counts: dict[int, int] = {}
    for y_key in row_ys:
        row_chars = [c for c in chars if round(c["top"] / 3) * 3 == y_key]
        row_border_counts[y_key] = sum(
            1 for c in row_chars if c.get("text", "") in _PIPE_CHARS or c.get("text", "") in _HLINE_CHARS
        )

    cuts = [row_ys[0]]
    for i in range(1, len(row_ys)):
        y_gap = row_ys[i] - row_ys[i - 1]
        is_gap = y_gap > gap_threshold

        # structural cut: split when transitioning between bordered (table) and non-bordered (text) rows
        cur_has_borders = row_border_counts.get(row_ys[i], 0) >= 3
        prev_has_borders = row_border_counts.get(row_ys[i - 1], 0) >= 3
        is_structural_cut = cur_has_borders != prev_has_borders

        if not is_gap and not is_structural_cut and row_ys[i] in row_font_sizes and row_ys[i - 1] in row_font_sizes:
            if abs(row_font_sizes[row_ys[i]] - row_font_sizes[row_ys[i - 1]]) > 2.0:
                is_gap = True

        if is_gap or is_structural_cut:
            cuts.append(row_ys[i - 1])
            cuts.append(row_ys[i])
    cuts.append(row_ys[-1])

    bands = []
    for i in range(0, len(cuts) - 1, 2):
        bands.append((cuts[i], cuts[i + 1]))
    if not bands:
        bands = [(row_ys[0], row_ys[-1])]

    # Track which band start y-values came from structural cuts
    structural_cut_ys = set()
    for i in range(1, len(row_ys)):
        y_gap = row_ys[i] - row_ys[i - 1]
        is_gap = y_gap > gap_threshold
        cur_has = row_border_counts.get(row_ys[i], 0) >= 3
        prev_has = row_border_counts.get(row_ys[i - 1], 0) >= 3
        if cur_has != prev_has:
            structural_cut_ys.add(row_ys[i])

    zones = []
    for y_start, y_end in bands:
        margin = 5
        band_chars = [c for c in chars if y_start - margin <= c["top"] <= y_end + margin]
        band_rects = [r for r in rects if y_start - margin <= r["top"] <= y_end + margin]
        if not band_chars:
            continue
        x0 = min(c["x0"] for c in band_chars)
        x1 = max(c["x1"] for c in band_chars)
        text = "".join(c["text"] for c in sorted(band_chars, key=lambda c: (c["top"], c["x0"])))
        zone = Zone(
            type="unknown",
            bbox=(x0, y_start, x1, y_end),
            page=page_idx,
            chars=band_chars,
            rects=band_rects,
            text=text.strip(),
        )
        _zone_border_count = sum(
            1 for c in zone.chars if c.get("text", "") in _PIPE_CHARS or c.get("text", "") in _HLINE_CHARS
        )
        zone.type = _classify_zone_legacy(
            zone,
            page_h,
            _PIPE_CHARS,
            _KNOWN_HEADER_WORDS,
            is_border_zone=(_zone_border_count >= 10),
            has_structural_context=bool(structural_cut_ys),
        )
        zones.append(zone)

    # Merge adjacent data_table zones ONLY if not separated by a structural cut
    merged = []
    for z in zones:
        if merged and z.type == "data_table" and merged[-1].type == "data_table" and z.bbox[1] not in structural_cut_ys:
            prev = merged[-1]
            prev.bbox = (min(prev.bbox[0], z.bbox[0]), prev.bbox[1], max(prev.bbox[2], z.bbox[2]), z.bbox[3])
            prev.chars.extend(z.chars)
            prev.rects.extend(z.rects)
            prev.text += z.text
        else:
            merged.append(z)
    return merged


def _classify_zone_legacy(
    zone: Zone,
    page_h: float,
    pipe_chars: set,
    known_header_words: set,
    is_border_zone: bool = False,
    has_structural_context: bool = False,
) -> str:
    """Legacy zone classifier — used only by _legacy_y_band_zones fallback.

    Args:
        is_border_zone: True if this zone contains ≥10 structural border chars.
        has_structural_context: True when structural cuts exist on this page,
            meaning a bordered table was detected. Non-bordered zones adjacent
            to bordered tables are metadata, not tables.
    """
    y_ratio = zone.bbox[1] / page_h if page_h else 0
    text = zone.text
    char_count = len(zone.chars)

    if y_ratio > 0.85 and char_count < 30 and "页" in text:
        return "footer"

    # Bordered zone → always data_table
    if is_border_zone:
        return "data_table"

    # Non-bordered zone adjacent to a bordered table → metadata, not table
    if has_structural_context and not is_border_zone:
        if re.search(r"[\u4e00-\u9fff][：:]", text):
            return "summary"
        return "summary"

    pipe_count = sum(1 for c in zone.chars if c.get("text") in pipe_chars)
    if pipe_count >= 10:
        return "data_table"
    if bool(re.search(r"\d{8}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", text)) and bool(
        re.search(r"(?:RMB|USD|CNY)\s*[\d,.]+|\d+\.\d{2}", text)
    ):
        return "data_table"
    _vocab_hits = sum(1 for w in known_header_words if w in text)
    if _vocab_hits >= 3:
        return "data_table"
    if y_ratio < 0.15 and char_count < 80:
        if not re.search(r"[\u4e00-\u9fff][：:]", text):
            return "title"
    if char_count < 300 and re.search(r"[\u4e00-\u9fff][：:]", text):
        return "summary"
    row_ys = sorted(set(round(c["top"] / 3) * 3 for c in zone.chars))
    if len(row_ys) < 2 and not any(ch.isdigit() for ch in text):
        return "summary"
    x_positions = set(round(c["x0"] / 10) * 10 for c in zone.chars)
    if len(x_positions) >= 5 and char_count > 20:
        return "data_table"
    if len(zone.rects) >= 3:
        return "data_table"
    if len(row_ys) >= 3:
        return "data_table"
    return "unknown"
