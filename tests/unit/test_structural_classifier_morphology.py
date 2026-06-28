# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.structure.analysis.structural_classifier import score_page_morphology_from_bundles


def test_score_page_morphology_from_bundles():
    bundles = [
        {
            "page": 4,
            "region_detect": {
                "region_detect_candidates": [
                    {"kind": "field_grid", "score": 0.85},
                    {"kind": "micro_grid", "score": 0.72},
                ]
            },
        }
    ]
    scores = score_page_morphology_from_bundles(bundles)
    assert scores["H_field_grid"] == 0.85
    assert scores["H_micro_grid"] == 0.72
