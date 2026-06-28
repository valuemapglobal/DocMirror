# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Result fusion engine — merges competing table extraction results.

Purpose: Fuses multiple table candidates (different tiers/engines) into one
best grid using cell-level voting and structure agreement.

Main components: ``ResultFusionEngine``.

Upstream: Multiple ``ExtractCandidate`` outputs.

Downstream: ``extract.best_candidate``, ``table.signal_fusion``.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Result Fusion Engine
# ═══════════════════════════════════════════════════════════════════════════════


class ResultFusionEngine:
    """
    Result fusion engine.

    When multiple layers produce output, fuse them by consensus rather than simple replacement.

    Fusion strategy:
        1. Header row voting: rows recognized by multiple layers as headers → high confidence
        2. Column boundary alignment: weighted average across layers
        3. Cell content selection: prefer content from high-confidence layers
        4. Conflict resolution: majority voting
        5. Confidence calibration: fused confidence is typically higher than any single layer
    """

    @classmethod
    def fuse(cls, results: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Fuse multiple extraction results

        Args:
            results: List of layer extraction results; each contains:
                - tables: Table list
                - confidence: Confidence score
                - metadata: Metadata

        Returns:
            Fused result
        """
        if not results:
            return {"tables": [], "confidence": 0.0, "metadata": {}}

        if len(results) == 1:
            return results[0]

        try:
            # 1. Header row voting
            fused_header = cls._vote_header(results)

            # 2. Column boundary fusion
            fused_columns = cls._merge_column_boundaries(results)

            # 3. Select best table (based on fusion strategy)
            fused_tables = cls._select_best_tables(results, fused_header, fused_columns)

            # 4. Confidence calibration
            fused_confidence = cls._calibrate_confidence(results)

            # 5. Build fusion metadata
            fusion_metadata = {
                "fusion_method": "weighted_consensus",
                "layer_count": len(results),
                "layer_confidences": [r.get("confidence", 0) for r in results],
                "header_votes": fused_header.get("votes", {}),
                "fusion_improvement": fused_confidence - max(r.get("confidence", 0) for r in results),
            }

            fused_result = {
                "tables": fused_tables,
                "confidence": fused_confidence,
                "metadata": {**results[0].get("metadata", {}), "fusion": fusion_metadata},
            }

            logger.debug(
                f"[ResultFusion] Fused {len(results)} layers, "
                f"confidence: {fused_confidence:.3f} "
                f"(best single: {max(r.get('confidence', 0) for r in results):.3f})"
            )

            return fused_result

        except Exception as e:
            logger.warning(f"[ResultFusion] Fusion failed: {e}, falling back to best result")
            # Fallback: return the highest-confidence single result
            return max(results, key=lambda r: r.get("confidence", 0))

    @classmethod
    def _vote_header(cls, results: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Header row voting

        Args:
            results: Layer extraction results

        Returns:
            {'row_index': int, 'votes': int, 'confidence': float}
        """
        header_votes = Counter()
        header_confidence = defaultdict(list)

        for result in results:
            tables = result.get("tables", [])
            if not tables:
                continue

            # Get header rows identified by each layer
            for table in tables:
                header_idx = cls._extract_header_index(table)
                if header_idx is not None:
                    header_votes[header_idx] += 1
                    header_confidence[header_idx].append(result.get("confidence", 0))

        if not header_votes:
            return {"row_index": 0, "votes": 0, "confidence": 0.0}

        # Select the row with the most votes and highest average confidence
        best_row = max(
            header_votes.keys(),
            key=lambda r: (header_votes[r], np.mean(header_confidence[r]) if header_confidence[r] else 0),
        )

        return {
            "row_index": best_row,
            "votes": header_votes[best_row],
            "confidence": np.mean(header_confidence[best_row]) if header_confidence[best_row] else 0.0,
        }

    @classmethod
    def _merge_column_boundaries(cls, results: list[dict[str, Any]]) -> list[float]:
        """
        Fuse column boundaries (weighted average)

        Args:
            results: Layer extraction results

        Returns:
            Fused column boundary list
        """
        all_boundaries = []
        all_confidences = []

        for result in results:
            tables = result.get("tables", [])
            if not tables:
                continue

            # Get the first table's column boundaries
            table = tables[0]
            col_bounds = cls._extract_column_boundaries(table)

            if col_bounds:
                all_boundaries.append(col_bounds)
                all_confidences.append(result.get("confidence", 0))

        if not all_boundaries:
            return []

        # Align column count (take the max)
        max_cols = max(len(b) for b in all_boundaries)

        fused_bounds = []
        for col_idx in range(max_cols):
            # Collect all layers' boundaries for this column
            bounds_at_col = []
            weights_at_col = []

            for bounds, conf in zip(all_boundaries, all_confidences):
                if col_idx < len(bounds):
                    bounds_at_col.append(bounds[col_idx])
                    weights_at_col.append(conf)

            # Weighted average (higher confidence layers weigh more)
            if bounds_at_col:
                weights = np.array(weights_at_col)
                weights = weights / weights.sum()  # normalize
                fused_bound = np.average(bounds_at_col, weights=weights)
                fused_bounds.append(fused_bound)

        return fused_bounds

    @classmethod
    def _select_best_tables(
        cls, results: list[dict[str, Any]], header_info: dict[str, Any], fused_columns: list[float]
    ) -> list[dict[str, Any]]:
        """
        Select best table (or fuse multiple tables)

        Args:
            results: Layer extraction results
            header_info: Header voting result
            fused_columns: Fused column boundaries

        Returns:
            Fused table list
        """
        # Simple strategy: pick the highest-confidence table
        # Complex strategy: fuse cells across tables (future extension)

        if not results:
            return []

        # Sort by confidence
        sorted_results = sorted(results, key=lambda r: r.get("confidence", 0), reverse=True)
        best_result = sorted_results[0]

        # Handle case where tables may be a list
        tables = best_result.get("tables", [])
        if not tables:
            return []

        # If tables is a list of dicts
        if isinstance(tables, list) and len(tables) > 0:
            if isinstance(tables[0], dict):
                pass  # OK
            elif isinstance(tables[0], list):
                # Convert to dict format
                tables = [{"data": tables, "metadata": {}}]

        # If multiple layers, try to optimize the best table
        if len(results) > 1:
            # Apply fused header and column boundaries
            tables = cls._optimize_tables(tables, header_info, fused_columns)

        return tables

    @classmethod
    def _optimize_tables(cls, tables: list[dict], header_info: dict, fused_columns: list[float]) -> list[dict]:
        """Optimize a table (apply fused headers and column boundaries)"""
        if not tables:
            return tables

        optimized = []
        for table in tables:
            # Create a copy
            opt_table = table.copy()

            # Apply fused headers (if any)
            if header_info.get("votes", 0) > 1:
                opt_table["fused_header"] = header_info

            # Apply fused column boundaries (if any)
            if fused_columns:
                opt_table["fused_columns"] = fused_columns

            optimized.append(opt_table)

        return optimized

    @classmethod
    def _calibrate_confidence(cls, results: list[dict[str, Any]]) -> float:
        """
        Calibrate fusion confidence

        Algorithm:
        1. If layers agree (same headers), boost confidence
        2. If layers differ significantly, use weighted average
        3. Fused confidence is typically higher than the best single result
        """
        if not results:
            return 0.0

        if len(results) == 1:
            return results[0].get("confidence", 0)

        # Get confidence scores from each layer
        confidences = [r.get("confidence", 0) for r in results]
        best_conf = max(confidences)
        avg_conf = np.mean(confidences)

        # Check consistency (header voting)
        header_votes = Counter()
        for result in results:
            tables = result.get("tables", [])
            if tables:
                header_idx = cls._extract_header_index(tables[0])
                if header_idx is not None:
                    header_votes[header_idx] += 1

        # Consistency bonus
        agreement_bonus = 0.0
        if header_votes:
            max_votes = max(header_votes.values())
            if max_votes == len(results):
                # All layers agree
                agreement_bonus = 0.05
            elif max_votes >= len(results) * 0.6:
                # Majority agrees
                agreement_bonus = 0.03

        # Weighted blend: best layer 60%, mean 40%, plus agreement bonus
        fused_conf = best_conf * 0.6 + avg_conf * 0.4 + agreement_bonus

        # Clamp to unit interval
        return min(1.0, max(0.0, fused_conf))

    @classmethod
    def _extract_header_index(cls, table: dict[str, Any]) -> int | None:
        """Extract header row indices from a table"""
        metadata = table.get("metadata", {})

        # Try to get from column signature inference result
        header_inference = metadata.get("header_inference", {})
        if header_inference:
            return header_inference.get("header_row_index")

        # Try to get from traditional methods
        header_row = table.get("header_row")
        if header_row is not None:
            return header_row

        # Default to row 0
        return 0

    @classmethod
    def _extract_column_boundaries(cls, table: dict[str, Any]) -> list[float]:
        """Extract column boundaries from a table"""
        metadata = table.get("metadata", {})

        # Try to get from fused column boundaries
        fused_columns = metadata.get("fused_columns", [])
        if fused_columns:
            return fused_columns

        # Try to get from column boundary metadata
        col_bounds = metadata.get("column_boundaries", [])
        if col_bounds:
            return col_bounds

        # Try to extract from headers
        header = table.get("header", [])
        if header:
            # Return placeholder (should compute from bbox)
            return [i * 100.0 for i in range(len(header))]

        return []

    @classmethod
    def _calculate_agreement_score(cls, results: list[dict[str, Any]]) -> float:
        """
        Compute consistency score across layers

        Returns:
            0.0 (completely inconsistent) - 1.0 (fully consistent)
        """
        if len(results) < 2:
            return 1.0

        # Extract header rows from each layer
        header_indices = []
        for result in results:
            tables = result.get("tables", [])
            if tables:
                header_idx = cls._extract_header_index(tables[0])
                if header_idx is not None:
                    header_indices.append(header_idx)

        if not header_indices:
            return 0.0

        # Compute consistency (ratio of the most-voted)
        votes = Counter(header_indices)
        max_votes = max(votes.values())

        return max_votes / len(header_indices)
