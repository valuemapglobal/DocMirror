# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Governance tests for privacy-safe private credit-report goldens."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests._credit_report_golden import compare_output_to_case, sha256_file

_FIXTURE_DIR = Path("tests/fixtures-private/credit_report")
_MANIFEST = _FIXTURE_DIR / "golden" / "manifest.json"


def _manifest() -> dict:
    if not _MANIFEST.exists():
        pytest.skip("private credit-report golden manifest is unavailable")
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


def test_credit_report_golden_manifest_is_private_traceable_and_unambiguous() -> None:
    manifest = _manifest()
    sources = manifest["sources"]
    cases = manifest["cases"]
    source_hashes = {sha256_file(path) for path in _FIXTURE_DIR.glob("*.pdf")}
    inventory_hashes = {source["source_sha256"] for source in sources}
    case_hashes = {case["source_sha256"] for case in cases}
    source_by_hash = {source["source_sha256"]: source for source in sources}

    assert manifest["schema_version"] == "credit_report.golden.v2"
    assert len(sources) == len(source_hashes)
    assert len(inventory_hashes) == len(sources)
    assert inventory_hashes == source_hashes
    assert len({case["case_id"] for case in cases}) == len(cases)
    assert len(case_hashes) == len(cases)
    assert case_hashes <= inventory_hashes
    assert all(source["disposition"] in {"golden_candidate", "golden_approved", "inventory_only"} for source in sources)
    assert all(
        source_by_hash[case["source_sha256"]]["disposition"]
        == ("golden_approved" if case["review_status"] == "approved" else "golden_candidate")
        for case in cases
    )
    assert all(
        source["source_sha256"] not in case_hashes for source in sources if source["disposition"] == "inventory_only"
    )
    assert all(source.get("reason") for source in sources if source["disposition"] == "inventory_only")
    assert all("source_file" not in case and "subject_name" not in case for case in cases)
    assert all("source_file" not in source and "subject_name" not in source for source in sources)
    assert all(case["review_status"] in {"candidate", "approved"} for case in cases)
    assert all(case["review_status"] != "approved" or case["truth_scope"] == "complete" for case in cases)


def test_credit_report_golden_comparator_requires_every_declared_fact() -> None:
    output = {
        "data": {
            "fields": {},
            "credit_accounts": [{"normalized": {"account_id": "a-1"}}],
            "overdue_records": [],
        }
    }
    case = {"expected": {"counts": {"credit_accounts": 1, "overdue_records": 1}}}

    comparison = compare_output_to_case(output, case)

    assert comparison["exact"] is False
    assert comparison["precision"] == 0.5
    assert comparison["mismatches"][0]["path"] == "counts.overdue_records"


def test_no_unreviewed_candidate_can_claim_100_percent_precision() -> None:
    manifest = _manifest()
    approved = [case for case in manifest["cases"] if case["review_status"] == "approved"]

    if not approved:
        pytest.skip("No human-approved complete credit-report golden exists yet")
    assert all(case["truth_scope"] == "complete" for case in approved)
