# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Hypothesis annex + MO detect audit tests (Design 20 residual)."""

from __future__ import annotations

from docmirror.topology.page_projection.hypothesis_annex import build_document_hypothesis_annex
from docmirror.topology.page_projection.morphology_orchestrator import write_detect_audit_to_bundle


def test_write_detect_audit_to_bundle():
    bundle = {
        "page": 4,
        "region_detect": {
            "region_detect_candidates": [
                {"candidate_id": "cand_fg", "kind": "field_grid", "score": 0.8, "bbox": [0, 0, 10, 10]},
            ]
        },
    }
    write_detect_audit_to_bundle(bundle)
    detect_only = (bundle.get("audit") or {}).get("detect_only") or []
    assert len(detect_only) == 1
    assert detect_only[0]["materialize_skipped_reason"] == "not_materialized"


def test_hypothesis_annex_quarantine_cells():
    ds = {
        "_page_evidence_bundles": [
            {
                "page": 4,
                "local_structure_evidence": {
                    "structures": [
                        {
                            "structure_id": "ls_p4_0",
                            "cells": [
                                {
                                    "cell_id": "c0",
                                    "geometry_status": "quarantined",
                                    "quarantine_reason": "type_mismatch",
                                    "label_text": "管理机构",
                                    "text": "bad",
                                }
                            ],
                        }
                    ],
                },
            }
        ]
    }
    annex = build_document_hypothesis_annex(ds)
    quarantined = [a for a in annex if a.get("hypothesis_kind") == "quarantined_cell"]
    assert len(quarantined) == 1
    assert quarantined[0]["reason"] == "type_mismatch"
