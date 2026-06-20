# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Profile run state — mutable cross-page extraction state.

Purpose: Tracks ledger continuation, template width, and per-document flags
shared across pages during one extraction run.

Main components: ``ProfileRunState``.

Upstream: ``pipeline.context``, ``document_profile`` binding.

Downstream: ``PagePipeline``, ``extract.template_injector``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docmirror.models.entities.extraction_profile import ExtractionProfile


class ProfileRunState:
    """Tracks candidates and gating when ExtractionProfile is active."""

    def __init__(self, profile: ExtractionProfile | None, audit_out: list | None, audit_page: int | None = None):
        from .best_candidate import ExtractCandidate

        self.profile = profile
        self.audit_out = audit_out
        self.audit_page = audit_page
        self.candidates: list = []
        self._ExtractCandidate = ExtractCandidate
        self.disabled = set(profile.table_disabled_layers()) if profile else set()
        self.min_conf = profile.effective_min_confidence() if profile else 0.0
        self.use_bcs = profile.should_use_bcs() if profile else False
        self.picked: tuple | None = None

    def layer_disabled(self, layer: str) -> bool:
        return layer in self.disabled

    def offer(self, tables: list, layer: str, conf: float) -> bool:
        """Record candidate; return True if extraction should stop now."""
        if not self.profile:
            return True
        row_count = len(tables[0]) if tables and tables[0] else 0
        self.candidates.append(self._ExtractCandidate(tables=tables, layer=layer, confidence=conf, row_count=row_count))
        if self.use_bcs:
            return False
        if self.min_conf > 0 and conf < self.min_conf:
            return False
        return True

    def finalize(self, default_tables: list, default_layer: str, default_conf: float):
        from .best_candidate import count_data_rows, pick_best_candidate

        if not self.profile or not self.candidates:
            return default_tables, default_layer, default_conf

        oracle_rows = 0
        if self.use_bcs and self.profile.bcs_oracle_layer:
            for c in self.candidates:
                if c.layer == "pipe_delimited" and c.row_count >= 2:
                    oracle_rows = count_data_rows(c.tables[0] if c.tables else [])
                    break
            if oracle_rows == 0:
                for c in self.candidates:
                    if c.layer == self.profile.bcs_oracle_layer:
                        oracle_rows = count_data_rows(c.tables[0] if c.tables else [])
                        break
            if oracle_rows == 0:
                oracle_rows = max((c.row_count for c in self.candidates), default=0)

        if self.use_bcs:
            pick = pick_best_candidate(self.candidates, self.profile, oracle_rows=oracle_rows)
            if pick:
                c = pick.candidate
                if self.audit_out is not None:
                    entry: dict = {
                        "picked": c.layer,
                        "score": round(pick.score, 4),
                        "row_count": c.row_count,
                        "candidates": [
                            {"layer": x.layer, "rows": x.row_count, "conf": round(x.confidence, 3)}
                            for x in pick.all_candidates
                        ],
                    }
                    if self.audit_page is not None:
                        entry["page"] = self.audit_page
                    self.audit_out.append(entry)
                return c.tables, c.layer, c.confidence

        best = max(self.candidates, key=lambda c: (c.confidence, c.row_count))
        return best.tables, best.layer, best.confidence

    def pick_oracle_layer(
        self,
        *,
        layer: str,
        mark_fast_continuation: bool = False,
    ) -> tuple[list, str, float] | None:
        """Return the first valid candidate for ``layer`` (ledger continuation fast path)."""
        for c in reversed(self.candidates):
            if c.layer != layer or c.row_count < 2:
                continue
            if self.audit_out is not None:
                entry: dict = {
                    "picked": c.layer,
                    "score": 1.0,
                    "row_count": c.row_count,
                    "candidates": [
                        {
                            "layer": c.layer,
                            "rows": c.row_count,
                            "conf": round(c.confidence, 3),
                        }
                    ],
                }
                if mark_fast_continuation:
                    entry["fast_continuation"] = True
                if self.audit_page is not None:
                    entry["page"] = self.audit_page
                self.audit_out.append(entry)
            return c.tables, c.layer, c.confidence
        return None
