# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
GA1.0-02: Geometry Column Reconstruction (GCR) — Universal Column Detection

Replaces three incompatible column-detection algorithms (QGE fixed-gap,
GR relative-gap, field_grid label-bisection) with one geometry-first algorithm.

Algorithm (two-pass):

    Pass 1 — Per-Line X-Gap Clustering (Otsu-like threshold)
        For each text line (Y-clustered tokens), compute X-gaps and find an
        adaptive split that minimizes intra-class variance between "within-column"
        and "between-column" gaps.

    Pass 2 — Cross-Line Consistency Voting
        Cluster column-boundary X positions across all body lines and accept
        boundaries that appear in >= 60% of lines. This eliminates false
        positives from merged cells and anomalous spacing.

Public API::

    columns = GCRColumns.from_tokens(tokens)
    col_groups = GCRColumns.split_line(line_tokens)
    bands = columns.to_col_bands()
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from docmirror.ocr.micro_grid.models import OCRToken

logger = logging.getLogger(__name__)


@dataclass
class ColumnBand:
    """One column band derived from GCR analysis."""
    col_index: int
    x_start: float
    x_end: float
    support_ratio: float = 1.0
    confidence: float = 1.0


@dataclass
class GCRColumns:
    """Result of a full two-pass Geometry Column Reconstruction.

    Stores per-line column groupings and aggregated column bands.
    """
    col_bands: list[ColumnBand] = field(default_factory=list)
    per_line_boundaries: list[list[float]] = field(default_factory=list)
    num_lines_analyzed: int = 0
    num_boundaries_found: int = 0

    # ── Public API ──────────────────────────────────────────────────────────

    @staticmethod
    def from_tokens(
        tokens: list[OCRToken],
        min_support: float = 0.6,
        cluster_tolerance: float = 5.0,
        y_tolerance: float = 8.0,
        min_lines_for_voting: int = 3,
    ) -> GCRColumns:
        """Run full two-pass GCR on an OCRToken list.

        Pass 1: Y-cluster into lines -> per-line Otsu-like X-gap split.
        Pass 2: Cross-line boundary voting.

        Args:
            tokens: Flat list of OCRToken objects.
            min_support: Minimum fraction of lines that must agree on a
                boundary position (default 0.6 = 60%).
            cluster_tolerance: Max pixel distance to cluster nearby boundaries
                (default 5.0 px).
            y_tolerance: Max vertical distance (px) to group tokens into a row.
            min_lines_for_voting: Minimum lines needed before voting is
                meaningful (default 3). Below this, all per-line boundaries
                are accepted on their own merit.

        Returns:
            GCRColumns with col_bands populated.
        """
        if not tokens or len(tokens) < 2:
            return GCRColumns()

        # Pass 1a: Y-cluster into lines
        lines = GCRColumns._group_tokens_into_rows(tokens, y_tolerance)
        if len(lines) < 2:
            return GCRColumns()

        # Pass 1b: Per-line X-gap clustering
        per_line_boundaries: list[list[float]] = []
        for line in lines:
            boundaries = GCRColumns._cluster_line_boundaries(line)
            per_line_boundaries.append(boundaries if boundaries else [])

        # Pass 2: Cross-line consistency voting
        if len([b for b in per_line_boundaries if b]) < min_lines_for_voting:
            # Not enough lines for meaningful voting -- accept all boundaries
            # from the most-complete line
            complete_lines = [b for b in per_line_boundaries if b]
            if not complete_lines:
                return GCRColumns()
            best_line = max(complete_lines, key=len)
            col_bands = GCRColumns._boundaries_to_bands(best_line, lines)
            return GCRColumns(
                col_bands=col_bands,
                per_line_boundaries=per_line_boundaries,
                num_lines_analyzed=len(lines),
                num_boundaries_found=len(best_line),
            )

        accepted_boundaries = GCRColumns._align_boundaries_across_lines(
            per_line_boundaries, min_support, cluster_tolerance
        )

        col_bands = GCRColumns._boundaries_to_bands(accepted_boundaries, lines)

        return GCRColumns(
            col_bands=col_bands,
            per_line_boundaries=per_line_boundaries,
            num_lines_analyzed=len(lines),
            num_boundaries_found=len(accepted_boundaries),
        )

    @staticmethod
    def split_line(
        tokens_or_cells: list[Any],
    ) -> list[list[Any]]:
        """Single-line column partition (GR/QGE compatibility).

        Takes a list of objects that each have an ``x0`` and ``x1`` attribute
        (or duck-typed bbox tuple access), and partitions them into column
        groups using the Otsu-like gap clustering.

        Args:
            tokens_or_cells: List of OCRToken, _Cell, or similar with bbox.

        Returns:
            List of lists, each inner list being one column's items.
        """
        if not tokens_or_cells or len(tokens_or_cells) < 2:
            return [list(tokens_or_cells)] if tokens_or_cells else []

        # Generic x0/x1 accessor
        def _get_x0(item: Any) -> float:
            if hasattr(item, "bbox"):
                return float(item.bbox[0])
            if hasattr(item, "x0"):
                return float(item.x0)
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                return float(item[0])
            return 0.0

        def _get_x1(item: Any) -> float:
            if hasattr(item, "bbox"):
                return float(item.bbox[2])
            if hasattr(item, "x1"):
                return float(item.x1)
            if isinstance(item, (list, tuple)) and len(item) >= 4:
                return float(item[2])
            return 0.0

        # Sort by x position
        sorted_items = sorted(tokens_or_cells, key=_get_x0)

        # Compute X-gaps
        gaps: list[tuple[float, int]] = []  # (gap_size, index_before_gap)
        for i in range(1, len(sorted_items)):
            gap = _get_x0(sorted_items[i]) - _get_x1(sorted_items[i - 1])
            if gap > 0:
                gaps.append((gap, i))

        if not gaps:
            return [sorted_items]

        # Otsu-like threshold: find best split point
        gap_values = [g[0] for g in gaps]
        threshold = GCRColumns._otsu_threshold(gap_values)

        if threshold is None:
            return [sorted_items]

        # Partition at gaps above threshold
        columns: list[list[Any]] = []
        current = [sorted_items[0]]
        for gap_size, idx in gaps:
            if gap_size > threshold:
                columns.append(current)
                current = [sorted_items[idx]]
            else:
                current.append(sorted_items[idx])
        if current:
            columns.append(current)

        return columns

    def to_col_bands(self) -> list[dict[str, Any]]:
        """Export to field_grid col_bands format.

        Returns a list of dicts::

            [{"start": x_start, "end": x_end, "confidence": c, ...}, ...]
        """
        return [
            {
                "start": b.x_start,
                "end": b.x_end,
                "col_index": b.col_index,
                "confidence": b.confidence,
                "support_ratio": b.support_ratio,
            }
            for b in self.col_bands
        ]

    # ── Internal: Pass 1 helpers ────────────────────────────────────────────

    @staticmethod
    def _group_tokens_into_rows(
        tokens: list[OCRToken],
        y_tolerance: float = 8.0,
    ) -> list[list[OCRToken]]:
        """Group tokens into text lines by Y-proximity."""
        if not tokens:
            return []

        sorted_tokens = sorted(tokens, key=lambda t: (t.bbox[1], t.bbox[0]))
        rows: list[list[OCRToken]] = [[sorted_tokens[0]]]

        for t in sorted_tokens[1:]:
            last_y = rows[-1][-1].bbox[1]
            if abs(t.bbox[1] - last_y) <= y_tolerance:
                rows[-1].append(t)
            else:
                rows.append([t])

        # Sort each row by X
        for row in rows:
            row.sort(key=lambda t: t.bbox[0])

        return rows

    @staticmethod
    def _cluster_line_boundaries(
        line_tokens: list[OCRToken],
    ) -> list[float]:
        """Detect column boundary X-positions within one line.

        Uses Otsu-like threshold on X-gaps between consecutive tokens.
        Returns sorted list of boundary X-coordinates.
        """
        if len(line_tokens) < 2:
            return []

        # Compute X-gaps
        gaps: list[float] = []
        for i in range(1, len(line_tokens)):
            gap = line_tokens[i].bbox[0] - line_tokens[i - 1].bbox[2]
            if gap > 0:
                gaps.append(gap)

        if not gaps:
            return []

        # Otsu-like threshold
        threshold = GCRColumns._otsu_threshold(gaps)
        if threshold is None:
            return []

        # Find boundary X positions for gaps exceeding threshold
        boundaries: list[float] = []
        for i, gap in enumerate(gaps):
            if gap > threshold:
                # Boundary X is the midpoint between the two tokens
                boundary_x = (line_tokens[i].bbox[2] + line_tokens[i + 1].bbox[0]) / 2.0
                boundaries.append(boundary_x)

        return boundaries

    @staticmethod
    def _otsu_threshold(values: list[float]) -> float | None:
        """Find the optimal split threshold using Otsu-like intra-class variance.

        Minimizes weighted sum of intra-class variances.  Returns the
        threshold value, or None if no meaningful split exists.
        """
        if len(values) < 4:
            if len(values) == 1:
                # Single gap between 2 items.
                # The median would equal the gap itself, making
                # ``gap > threshold`` always False (never split).
                #
                # Heuristic: if the single gap is large enough to be a
                # column boundary (>= 15px), return a slightly smaller
                # threshold so the gap exceeds it and we split.
                # Below that it is treated as within-column spacing.
                if values[0] >= 15.0:
                    return max(values[0] * 0.9, 2.0)
                return values[0]
            # 2-3 gaps between 3-4 items.
            # If all gaps are large (>= 15px), treat them all as column
            # boundaries by returning a threshold below the smallest gap.
            # Otherwise the median picks a meaningful split point.
            if all(v >= 15.0 for v in values):
                return max(min(values) * 0.9, 2.0)
            return statistics.median(values) if values else None

        sorted_vals = sorted(values)
        best_threshold = sorted_vals[-1]  # default: split at max
        best_variance = float("inf")

        for i in range(1, len(sorted_vals) - 1):
            threshold = sorted_vals[i]
            left = sorted_vals[:i]
            right = sorted_vals[i:]

            if not left or not right:
                continue

            var_left = statistics.variance(left) if len(left) > 1 else 0
            var_right = statistics.variance(right) if len(right) > 1 else 0
            weighted_var = len(left) * var_left + len(right) * var_right

            if weighted_var < best_variance:
                best_variance = weighted_var
                best_threshold = threshold

        # If best threshold is at the very end, it's not a real split
        if best_threshold >= sorted_vals[-1] * 0.9:
            # Try median-based fallback
            return statistics.median(sorted_vals)

        # Guard: threshold must be at least 2px to be meaningful
        return max(best_threshold, 2.0)

    # ── Internal: Pass 2 helpers ────────────────────────────────────────────

    @staticmethod
    def _align_boundaries_across_lines(
        per_line_boundaries: list[list[float]],
        min_support: float = 0.6,
        cluster_tolerance: float = 5.0,
    ) -> list[float]:
        """Vote on column boundaries across all lines.

        Clusters nearby boundary X-positions and accepts those with support
        from >= ``min_support`` fraction of lines.

        Returns sorted list of accepted boundary X-positions.
        """
        if not per_line_boundaries:
            return []

        # Collect all boundary positions
        all_boundaries = []
        for boundaries in per_line_boundaries:
            all_boundaries.extend(boundaries)

        if not all_boundaries:
            return []

        # Cluster nearby boundaries
        sorted_b = sorted(all_boundaries)
        clusters: list[list[float]] = [[sorted_b[0]]]

        for b in sorted_b[1:]:
            if b - clusters[-1][-1] <= cluster_tolerance:
                clusters[-1].append(b)
            else:
                clusters.append([b])

        # Count lines (rows with at least one boundary)
        num_lines = max(1, sum(1 for b in per_line_boundaries if b))

        # Accept clusters with sufficient support
        accepted: list[float] = []
        for cluster in clusters:
            cluster_mean = statistics.mean(cluster) if len(cluster) > 1 else cluster[0]
            support_count = 0
            for boundaries in per_line_boundaries:
                if boundaries and any(
                    abs(b - cluster_mean) <= cluster_tolerance for b in boundaries
                ):
                    support_count += 1

            if support_count / num_lines >= min_support:
                accepted.append(cluster_mean)

        return sorted(accepted)

    @staticmethod
    def _boundaries_to_bands(
        boundaries: list[float],
        lines: list[list[OCRToken]],
    ) -> list[ColumnBand]:
        """Convert sorted boundary X-positions to ColumnBand list."""
        if not lines:
            return []

        # Find overall X-range from all tokens
        all_x0 = [t.bbox[0] for row in lines for t in row]
        all_x1 = [t.bbox[2] for row in lines for t in row]
        doc_x0 = min(all_x0)
        doc_x1 = max(all_x1)

        if not boundaries:
            # Single column
            return [ColumnBand(col_index=0, x_start=doc_x0, x_end=doc_x1)]

        # Build bands between boundaries
        band_starts = [doc_x0] + boundaries
        band_ends = boundaries + [doc_x1]

        bands: list[ColumnBand] = []
        for idx, (start, end) in enumerate(zip(band_starts, band_ends)):
            if end - start < 1.0:
                continue  # Skip degenerate bands
            bands.append(ColumnBand(
                col_index=idx,
                x_start=start,
                x_end=end,
                confidence=1.0,
            ))

        return bands

    def __repr__(self) -> str:
        bands_str = ", ".join(
            f"Col{b.col_index}:({b.x_start:.0f}-{b.x_end:.0f})"
            for b in self.col_bands
        )
        return (
            f"GCRColumns({len(self.col_bands)} bands, "
            f"{self.num_lines_analyzed} lines, "
            f"[{bands_str}])"
        )
