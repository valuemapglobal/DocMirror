# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from scripts.validate.validate_core_contract_freeze import candidate_identity_errors
from scripts.validate.validate_p1_stability_readiness import version_identity_errors


def test_core_contract_candidate_must_match_package_version() -> None:
    assert candidate_identity_errors({"candidate": "1.1.0"}, "1.1.1") == [
        "core contract candidate 1.1.0 != package version 1.1.1"
    ]
    assert candidate_identity_errors({"candidate": "1.1.1"}, "1.1.1") == []


def test_every_release_evidence_version_must_match_package_version() -> None:
    errors = version_identity_errors(
        project_version="1.1.1",
        stability={"candidate": "1.1.0"},
        core_contract={"candidate": "1.2.0"},
        release={"version": "1.1.1"},
    )

    assert errors == [
        "stability evidence candidate 1.1.0 != package version 1.1.1",
        "core contract candidate 1.2.0 != package version 1.1.1",
    ]


def test_matching_release_identity_has_no_errors() -> None:
    assert (
        version_identity_errors(
            project_version="1.1.1",
            stability={"candidate": "1.1.1"},
            core_contract={"candidate": "1.1.1"},
            release={"version": "1.1.1"},
        )
        == []
    )
