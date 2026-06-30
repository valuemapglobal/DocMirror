# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Morphology Orchestrator (Design 20 Phase 1)."""

from __future__ import annotations

from docmirror.topology.page_projection.models import PageRegion
from docmirror.topology.page_projection.morphology_orchestrator import orchestrate_page_morphology


def _field_region(y0: float) -> PageRegion:
    return PageRegion(
        region_id=f"rg_p1_acc_{int(y0)}",
        kind="field_grid",
        morphology="S4",
        bbox=[0, y0, 100, y0 + 40],
        structure={"structure_kind": "field_grid", "cells": [{"label_text": "a", "text": "b"}]},
    )


def test_mo_table_led_skips_s4_regions():
    regions = [_field_region(10.0)]
    tables = [{"table_id": "pt_1_0", "headers": ["A"], "bbox": [0, 50, 100, 200]}]
    result = orchestrate_page_morphology(
        1,
        regions=regions,
        flow_texts=[],
        flow_key_values=[],
        tables=tables,
        content_type="table_dominant",
    )
    assert not any(b.morphology == "S4" for b in result.blocks)
    assert any(b.morphology == "S2" for b in result.blocks)
    assert result.audit.get("mo_skip_field_materialize") == "table_led_with_tables"


def test_mo_detect_only_audit():
    bundle = {
        "region_detect": {
            "region_detect_candidates": [
                {"candidate_id": "cand_1", "kind": "field_grid", "score": 0.7, "bbox": [0, 0, 10, 10]}
            ]
        }
    }
    result = orchestrate_page_morphology(
        4,
        regions=[],
        flow_texts=[],
        flow_key_values=[],
        tables=[],
        evidence_bundle=bundle,
        content_type="scan_led",
    )
    detect_only = result.audit.get("detect_only") or []
    assert len(detect_only) == 1
    assert detect_only[0].get("materialize_skipped_reason") == "not_materialized"
