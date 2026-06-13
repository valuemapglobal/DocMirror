# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Package cross-file consistency tests (EFPA P7 / L20)."""

from __future__ import annotations

from docmirror.core.package.consistency import evaluate_package_consistency
from docmirror.core.package.manifest import PackageManifest, check_package_consistency
from docmirror.models.entities.file_registry import FileRegistryEntry


def test_subject_name_mismatch_detected():
    manifest = PackageManifest(
        package_id="loan",
        files=[
            FileRegistryEntry(path="/a.pdf", extra={"subject_name": "张三"}),
            FileRegistryEntry(path="/b.pdf", extra={"subject_name": "李四"}),
        ],
    )
    hypos = evaluate_package_consistency(manifest)
    mismatch = [h for h in hypos if h.hypothesis_id == "subject_name_mismatch"]
    assert len(mismatch) == 1
    assert mismatch[0].passed is False
    assert mismatch[0].severity == "warning"


def test_subject_name_uniform_passes():
    manifest = PackageManifest(
        package_id="loan",
        files=[
            FileRegistryEntry(path="/a.pdf", extra={"subject_name": "张三"}),
            FileRegistryEntry(path="/b.pdf", extra={"subject_name": "张三"}),
        ],
    )
    hypos = evaluate_package_consistency(manifest)
    ok = [h for h in hypos if h.hypothesis_id == "subject_name_ok"]
    assert len(ok) == 1
    assert ok[0].passed is True


def test_check_package_consistency_wires_hypotheses():
    manifest = PackageManifest(
        package_id="loan",
        expected_document_types=["bank_statement"],
        files=[
            FileRegistryEntry(path="/a.pdf", extra={"document_type": "bank_statement", "subject_name": "张三"}),
            FileRegistryEntry(path="/b.pdf", extra={"document_type": "bank_statement", "subject_name": "李四"}),
        ],
    )
    out = check_package_consistency(manifest)
    assert out.consistency_hypotheses
    assert any("Multiple subject names" in issue for issue in out.consistency_issues)


def test_identity_number_mismatch_detected():
    manifest = PackageManifest(
        package_id="loan",
        files=[
            FileRegistryEntry(path="/a.pdf", extra={"证件号码": "110101199001011234"}),
            FileRegistryEntry(path="/b.pdf", extra={"证件号码": "110101199001019999"}),
        ],
    )
    hypos = evaluate_package_consistency(manifest)
    mismatch = [h for h in hypos if h.hypothesis_id == "identity_number_mismatch"]
    assert len(mismatch) == 1
    assert mismatch[0].passed is False


def test_identity_number_uniform_passes():
    manifest = PackageManifest(
        package_id="loan",
        files=[
            FileRegistryEntry(path="/a.pdf", extra={"identity_number": "91110108MA01234567"}),
            FileRegistryEntry(path="/b.pdf", extra={"统一社会信用代码": "91110108MA01234567"}),
        ],
    )
    hypos = evaluate_package_consistency(manifest)
    ok = [h for h in hypos if h.hypothesis_id == "identity_number_ok"]
    assert len(ok) == 1
    assert ok[0].passed is True
