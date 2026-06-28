#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Validate OSS 1.0 release readiness contracts."""

from __future__ import annotations

import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "docmirror" / "configs" / "release" / "oss_1_0_manifest.yaml"


def _load_manifest() -> dict[str, Any]:
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


def _load_pyproject() -> dict[str, Any]:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _docmirror_version() -> str:
    init_path = REPO_ROOT / "docmirror" / "__init__.py"
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', init_path.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise RuntimeError("docmirror/__init__.py does not define literal __version__")
    return match.group(1)


def validate_metadata(manifest: dict[str, Any], pyproject: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    project = pyproject["project"]
    expected_version = str(manifest["version"])
    if str(project.get("version")) != expected_version:
        errors.append(f"pyproject version {project.get('version')} != manifest {expected_version}")
    if _docmirror_version() != expected_version:
        errors.append(f"docmirror.__version__ {_docmirror_version()} != manifest {expected_version}")

    description = str(project.get("description", ""))
    category = manifest["position"]["category"]
    if category.lower() not in description.lower():
        errors.append(f"pyproject description must include category: {category}")

    all_deps = project.get("optional-dependencies", {}).get("all", [])
    forbidden = manifest["install_contract"]["public_all_must_not_include"]
    for dep in all_deps:
        for token in forbidden:
            if token in dep:
                errors.append(f"docmirror[all] must not include private dependency {token}: {dep}")
    return errors


def validate_required_files(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for rel in manifest.get("required_public_files", []):
        if not (REPO_ROOT / rel).is_file():
            errors.append(f"missing required public file: {rel}")
    return errors


def validate_public_positioning(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    docs = ["README.md", "README_zh-CN.md", "docs/quickstart.md", "docs/installation.md"]
    category = manifest["position"]["category"]
    tagline = manifest["position"]["tagline"]
    for rel in docs:
        path = REPO_ROOT / rel
        if not path.exists():
            errors.append(f"missing public doc: {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if rel.startswith("README") and category not in text:
            errors.append(f"{rel}: missing category phrase {category!r}")
        if rel.startswith("README") and tagline not in text:
            errors.append(f"{rel}: missing tagline {tagline!r}")
    return errors


def _archive_names(path: Path) -> list[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as zf:
            return zf.namelist()
    if path.suffixes[-2:] == [".tar", ".gz"]:
        with tarfile.open(path) as tf:
            return tf.getnames()
    return []


def validate_built_archives(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    dist = REPO_ROOT / "dist"
    if not dist.exists():
        return errors
    wheel_forbidden = manifest.get("wheel_forbidden_paths", [])
    sdist_forbidden = [
        "docmirror/plugins/.plugin_state.json",
        "docmirror_enterprise/",
        "docmirror_finance/",
        "docs/design/",
    ]
    for archive in sorted(dist.glob("docmirror-1.0.0*")):
        names = _archive_names(archive)
        forbidden = wheel_forbidden if archive.suffix == ".whl" else sdist_forbidden
        for name in names:
            normalized = name.split("/", 1)[1] if name.startswith("docmirror-1.0.0/") else name
            for prefix in forbidden:
                if normalized == prefix.rstrip("/") or normalized.startswith(prefix):
                    errors.append(f"{archive.name}: contains forbidden release path {normalized}")
    return errors


def validate_import_purity() -> list[str]:
    result = subprocess.run(
        [sys.executable, "scripts/validate/validate_import_purity.py"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return [(result.stderr or result.stdout).strip()]
    return []


def main() -> int:
    manifest = _load_manifest()
    pyproject = _load_pyproject()
    errors: list[str] = []
    for check in (
        lambda: validate_metadata(manifest, pyproject),
        lambda: validate_required_files(manifest),
        lambda: validate_public_positioning(manifest),
        lambda: validate_built_archives(manifest),
        validate_import_purity,
    ):
        errors.extend(check())

    if errors:
        print("OSS release validation FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("OSS release validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
