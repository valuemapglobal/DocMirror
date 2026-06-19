# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
ExtractionProfile — document-scoped orchestration for Core Extract (EPO).

Extends ``LayoutProfile`` with extraction-engine policy fields that control
page segmentation, best-candidate selection (BCS), normalization hooks, and
quality gates. All new fields default to values preserving generic pre-EPO
behaviour so existing profiles upgrade transparently.

Key policy areas::

    segmentation_mode          ZONE, FULL_PAGE_TABLE, or SECTION page splitting
    min_confidence_to_accept   Layer acceptance threshold (borderless ledgers: 0.85)
    enable_best_candidate_selection / bcs_oracle_layer   Multi-engine oracle path
    normalize_intracellular_newlines / collapse_duplicate_spaces   Cell cleanup
    merge_quarantine_on_col_mismatch   Cross-page merge safety
    enable_global_grid_tensor  Expensive char-scan signal (auto-disabled for oracle paths)

``from_layout_profile`` upgrades a base ``LayoutProfile`` to ``ExtractionProfile``
idempotently. Predicate helpers (``is_full_page_table``, ``needs_global_grid_tensor``,
``should_use_bcs``) encapsulate common routing decisions.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING


from docmirror.configs.models.layout_profile import LayoutProfile

if TYPE_CHECKING:
    pass


class SegmentationMode(str, Enum):
    """Page segmentation strategy for table extraction."""

    ZONE = "zone"
    FULL_PAGE_TABLE = "full_page_table"
    SECTION = "section"


class ExtractionProfile(LayoutProfile):
    """Extended layout profile driving zone + engine + normalize + merge policy.

    All new fields default to values that preserve generic (pre-EPO) behaviour.
    """

    segmentation_mode: SegmentationMode = SegmentationMode.ZONE
    zone_y_margin_pt: float = 0.0

    min_confidence_to_accept: float = 0.0
    enable_best_candidate_selection: bool = False
    bcs_oracle_layer: str | None = None
    max_engine_candidates: int = 3

    normalize_intracellular_newlines: bool = False
    collapse_duplicate_spaces: bool = False

    merge_quarantine_on_col_mismatch: bool = True

    expected_rows_per_page: float | None = None
    min_row_preservation_ratio: float = 0.995

    skip_pid_resample: bool = False
    enable_grid_template: bool = False
    enable_global_grid_tensor: bool = True
    table_normalize_hooks: list[str] | None = None
    use_tnp_staged: bool = False
    ocr_column_aware: bool = False

    @classmethod
    def from_layout_profile(cls, profile: LayoutProfile) -> ExtractionProfile:
        """Upgrade a LayoutProfile to ExtractionProfile (idempotent if already)."""
        if isinstance(profile, ExtractionProfile):
            return profile
        data = profile.model_dump()
        seg = data.get("segmentation_mode", SegmentationMode.ZONE)
        if isinstance(seg, str):
            try:
                data["segmentation_mode"] = SegmentationMode(seg)
            except ValueError:
                data["segmentation_mode"] = SegmentationMode.ZONE
        return cls(**data)

    def is_full_page_table(self) -> bool:
        return self.segmentation_mode == SegmentationMode.FULL_PAGE_TABLE

    def is_borderless_ledger(self) -> bool:
        return self.profile_id.startswith("borderless_ledger")

    def effective_min_confidence(self) -> float:
        """Minimum confidence before accepting a layer result."""
        if self.min_confidence_to_accept > 0:
            return self.min_confidence_to_accept
        if self.is_borderless_ledger():
            return 0.85
        return 0.0

    def should_use_bcs(self) -> bool:
        return self.enable_best_candidate_selection

    def needs_global_grid_tensor(self) -> bool:
        """Skip expensive 50-page char scan when oracle path does not use signal_processor."""
        if not self.enable_global_grid_tensor:
            return False
        if self.is_borderless_ledger() and self.bcs_oracle_layer == "pdfplumber_default":
            return False
        if "signal_processor" in self.table_disabled_layers():
            return False
        return True

    def table_x_right(self, page_width: float) -> float:
        """Effective right edge for table crop (sidebar noise exclusion)."""
        if self.sidebar_x_ratio and 0 < self.sidebar_x_ratio < 1:
            return page_width * self.sidebar_x_ratio
        return page_width
