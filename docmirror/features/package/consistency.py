# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Cross-file consistency hypotheses for file packages (L20 / P7)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from docmirror.features.package.manifest import PackageManifest


class ConsistencyHypothesis(BaseModel):
    """Cross-file consistency check result."""

    hypothesis_id: str
    check: str
    passed: bool = True
    severity: str = "info"
    message: str = ""
    file_paths: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


def _subject_name(entry: Any) -> str | None:
    extra = getattr(entry, "extra", None) or {}
    if not isinstance(extra, dict):
        return None
    for key in ("subject_name", "户名", "被查询人姓名", "企业名称"):
        val = extra.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    entities = extra.get("entities")
    if isinstance(entities, dict):
        for key in ("subject_name", "户名", "被查询人姓名"):
            val = entities.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _identity_number(entry: Any) -> str | None:
    extra = getattr(entry, "extra", None) or {}
    if not isinstance(extra, dict):
        return None
    for key in (
        "identity_number",
        "证件号码",
        "身份证号",
        "统一社会信用代码",
        "id_number",
    ):
        val = extra.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    entities = extra.get("entities")
    if isinstance(entities, dict):
        for key in ("identity_number", "证件号码", "身份证号", "统一社会信用代码"):
            val = entities.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def evaluate_package_consistency(manifest: PackageManifest) -> list[ConsistencyHypothesis]:
    """Run cross-file consistency checks beyond missing document types."""
    results: list[ConsistencyHypothesis] = []

    subjects: list[tuple[str, str]] = []
    for f in manifest.files:
        name = _subject_name(f)
        if name:
            subjects.append((f.path, name))

    if len(subjects) >= 2:
        unique = {name for _, name in subjects}
        if len(unique) > 1:
            results.append(
                ConsistencyHypothesis(
                    hypothesis_id="subject_name_mismatch",
                    check="subject_name_uniformity",
                    passed=False,
                    severity="warning",
                    message=f"Multiple subject names across package: {sorted(unique)}",
                    file_paths=[p for p, _ in subjects],
                    details={"subjects": dict(subjects)},
                )
            )
        else:
            results.append(
                ConsistencyHypothesis(
                    hypothesis_id="subject_name_ok",
                    check="subject_name_uniformity",
                    passed=True,
                    message=f"Subject name consistent: {next(iter(unique))}",
                    file_paths=[p for p, _ in subjects],
                )
            )

    identities: list[tuple[str, str]] = []
    for f in manifest.files:
        ident = _identity_number(f)
        if ident:
            identities.append((f.path, ident))

    if len(identities) >= 2:
        unique_id = {v for _, v in identities}
        if len(unique_id) > 1:
            results.append(
                ConsistencyHypothesis(
                    hypothesis_id="identity_number_mismatch",
                    check="identity_number_uniformity",
                    passed=False,
                    severity="warning",
                    message=f"Multiple identity numbers across package: {sorted(unique_id)}",
                    file_paths=[p for p, _ in identities],
                    details={"identities": dict(identities)},
                )
            )
        else:
            results.append(
                ConsistencyHypothesis(
                    hypothesis_id="identity_number_ok",
                    check="identity_number_uniformity",
                    passed=True,
                    message="Identity number consistent across package",
                    file_paths=[p for p, _ in identities],
                )
            )

    doc_types = [str(f.extra.get("document_type")) for f in manifest.files if f.extra.get("document_type")]
    if len(doc_types) != len(set(doc_types)) and doc_types:
        results.append(
            ConsistencyHypothesis(
                hypothesis_id="duplicate_document_types",
                check="document_type_diversity",
                passed=False,
                severity="info",
                message="Package contains duplicate document_type entries",
                details={"document_types": doc_types},
            )
        )

    return results
