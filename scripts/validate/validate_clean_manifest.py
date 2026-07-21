#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Validate the clean architecture manifest and stale architecture references."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.code_hygiene.allowlist import load_allowlist  # noqa: E402
from scripts.code_hygiene.clean_manifest import load_clean_manifest  # noqa: E402

TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".toml", ".json"}
SKIP_PARTS = {
    ".git",
    ".venv",
    ".deepseek",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".import_linter_cache",
    "node_modules",
    "docmirror_enterprise",
    "docmirror_finance",
    "output",
    "artifacts",
    "reports",
    "dist",
    "build",
}
DESIGN_HISTORY_PARTS = ("docs", "design")
REMOVED_REFERENCE_ALLOW_FILES = {
    "CHANGELOG.md",
    "docmirror/configs/architecture/clean_manifest.yaml",
    "docmirror/configs/architecture/domain_decomposition.yaml",
    "scripts/validate/validate_clean_manifest.py",
    "scripts/validate/validate_domain_decomposition.py",
    "scripts/validate/validate_structure_shims.py",
    "tests/contract/test_removed_import_paths.py",
    "tests/unit/test_architecture_a_contract.py",
    "tests/unit/test_community_default_delivery.py",
}


def _module_exists(module: str) -> bool:
    if not module.startswith("docmirror"):
        return False
    module_path = REPO_ROOT / Path(*module.split("."))
    return module_path.with_suffix(".py").is_file() or (module_path / "__init__.py").is_file()


def _iter_text_files() -> Iterable[Path]:
    for root, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [name for name in dirnames if name not in SKIP_PARTS]
        base = Path(root)
        if any(part in SKIP_PARTS for part in base.parts):
            continue
        for filename in filenames:
            path = base / filename
            if path.suffix not in TEXT_SUFFIXES:
                continue
            yield path


def _is_design_history(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT).parts
    return len(rel) >= 2 and rel[:2] == DESIGN_HISTORY_PARTS


def _path_spellings(module: str) -> set[str]:
    if not module.startswith("docmirror."):
        return {module}
    return {module, module.replace(".", "/")}


def validate_manifest_shape() -> list[str]:
    errors: list[str] = []
    manifest = load_clean_manifest()
    data = manifest.data
    if data.get("version") != 1:
        errors.append("clean_manifest.yaml: version must be 1")
    for key in (
        "layers",
        "public_modules",
        "dynamic_modules",
        "compatibility_modules",
        "removed_modules",
        "quarantine_modules",
    ):
        if key not in data:
            errors.append(f"clean_manifest.yaml: missing required section {key}")
    for item in data.get("quarantine_modules") or []:
        module = item.get("module")
        for key in ("owner", "reason", "exit_criteria", "review_by"):
            if not item.get(key):
                errors.append(f"clean_manifest.yaml: quarantine module {module} missing {key}")
    for layer_name, layer in (data.get("layers") or {}).items():
        for item in layer.get("import_linter_ignore_imports") or []:
            label = f"clean_manifest.yaml: layer {layer_name} import_linter_ignore_imports"
            for key in ("importer", "imported", "reason", "review_by"):
                if not item.get(key):
                    errors.append(f"{label} entry missing {key}: {item}")
    return errors


def validate_module_existence() -> list[str]:
    errors: list[str] = []
    manifest = load_clean_manifest()
    for section in ("public_modules", "dynamic_modules", "quarantine_modules"):
        for module in sorted(manifest.modules_for(section)):
            if not _module_exists(module):
                errors.append(f"{section}: module does not import/resolve: {module}")
    for module in sorted(manifest.removed_modules):
        if _module_exists(module):
            errors.append(f"removed_modules: old module still resolves: {module}")
    for module in sorted(manifest.compatibility_modules):
        if not _module_exists(module):
            errors.append(f"compatibility_modules: old module does not resolve: {module}")
    return errors


def validate_allowlist_modules() -> list[str]:
    errors: list[str] = []
    allow = load_allowlist()
    manifest = load_clean_manifest()
    live = manifest.live_modules
    for module in allow.get("orphan_modules", []) or []:
        if module in live or _module_exists(module):
            continue
        errors.append(f"allowlist orphan_modules contains stale non-importable module: {module}")
    return errors


def validate_removed_references() -> list[str]:
    errors: list[str] = []
    manifest = load_clean_manifest()
    removed = sorted(manifest.removed_modules)
    for path in _iter_text_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in REMOVED_REFERENCE_ALLOW_FILES:
            continue
        if _is_design_history(path):
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for module in removed:
            for spelling in _path_spellings(module):
                for lineno, line in enumerate(lines, start=1):
                    if "github.com/valuemapglobal/DocMirror/" in line:
                        continue
                    if spelling in line:
                        errors.append(f"{rel}:{lineno}: references removed path {spelling}")
    return errors


def validate_workflow_yaml() -> list[str]:
    errors: list[str] = []
    workflow_dir = REPO_ROOT / ".github" / "workflows"
    if not workflow_dir.is_dir():
        return errors
    for path in sorted(workflow_dir.glob("*.yml")) + sorted(workflow_dir.glob("*.yaml")):
        try:
            yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            errors.append(f"{path.relative_to(REPO_ROOT).as_posix()}: invalid YAML: {exc}")
    return errors


def validate_vnext_removed_imports() -> list[str]:
    from scripts.validate.validate_vnext_removed_imports import check, validate_baseline

    return check() + validate_baseline()


def main() -> int:
    errors: list[str] = []
    for check in (
        validate_manifest_shape,
        validate_module_existence,
        validate_allowlist_modules,
        validate_removed_references,
        validate_workflow_yaml,
        validate_vnext_removed_imports,
    ):
        errors.extend(check())

    if errors:
        print("Clean manifest validation FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("Clean manifest validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
