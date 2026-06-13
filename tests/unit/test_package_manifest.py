# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""PackageManifest tests (EFPA P5.4)."""

from __future__ import annotations

from docmirror.core.package.manifest import PackageManifest, check_package_consistency
from docmirror.models.entities.file_registry import FileRegistryEntry


def test_package_consistency_detects_missing_types():
    manifest = PackageManifest(
        package_id="loan_pkg",
        expected_document_types=["bank_statement", "credit_report"],
        files=[
            FileRegistryEntry(path="/a/bank.pdf", extra={"document_type": "bank_statement"}),
        ],
    )
    out = check_package_consistency(manifest)
    assert "credit_report" in out.missing_types
    assert not out.consistency_issues == []


def test_package_consistency_passes_when_complete():
    manifest = PackageManifest(
        package_id="loan_pkg",
        expected_document_types=["bank_statement"],
        files=[FileRegistryEntry(path="/a/bank.pdf", extra={"document_type": "bank_statement"})],
    )
    out = check_package_consistency(manifest)
    assert out.missing_types == []
    assert out.consistency_issues == []
    assert isinstance(out.consistency_hypotheses, list)
