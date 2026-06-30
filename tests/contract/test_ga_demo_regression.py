# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""GA 1.0 demo manifest contract."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_demo_manifest_references_valid_fixtures():
    """OUT5-3/4/5: ga_demo_manifest.yaml references existing fixture files."""
    from docmirror.configs.ga_experience import load_ga_demo_manifest
    data = load_ga_demo_manifest()
    demos = data.get("demos", {})
    assert len(demos) >= 3
    required = {"complex_pdf_to_rag", "bank_flow_to_finance_json", "low_quality_scan_to_partial_evidence"}
    for demo_id in required:
        assert demo_id in demos, f"missing demo: {demo_id}"
        demo = demos[demo_id]
        input_rel = demo.get("input", "")
        assert (REPO_ROOT / input_rel).is_file(), f"demo {demo_id}: fixture missing at {input_rel}"
        assert demo.get("command"), f"demo {demo_id}: missing command"
        assert demo.get("expected_artifacts"), f"demo {demo_id}: missing expected_artifacts"
