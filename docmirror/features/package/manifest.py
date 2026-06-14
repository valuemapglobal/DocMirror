# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Multi-file package manifest (L20 file bundle intelligence)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from docmirror.models.entities.file_registry import FileRegistryEntry


class PackageManifest(BaseModel):
    """A bundle of related documents."""

    package_id: str
    label: str = ""
    files: list[FileRegistryEntry] = Field(default_factory=list)
    expected_document_types: list[str] = Field(default_factory=list)
    missing_types: list[str] = Field(default_factory=list)
    consistency_issues: list[str] = Field(default_factory=list)
    consistency_hypotheses: list[dict[str, Any]] = Field(default_factory=list)


def check_package_consistency(manifest: PackageManifest) -> PackageManifest:
    """Check for missing expected types and basic cross-file issues."""
    found_types: set[str] = set()
    for f in manifest.files:
        dt = f.extra.get("document_type")
        if dt:
            found_types.add(str(dt))

    missing = [t for t in manifest.expected_document_types if t not in found_types]
    manifest.missing_types = missing
    if missing:
        manifest.consistency_issues.append(f"missing_document_types: {missing}")

    from docmirror.features.package.consistency import evaluate_package_consistency

    hypotheses = evaluate_package_consistency(manifest)
    manifest.consistency_hypotheses = [h.model_dump() for h in hypotheses]
    for h in hypotheses:
        if not h.passed and h.severity in ("warning", "error"):
            manifest.consistency_issues.append(h.message)

    return manifest
