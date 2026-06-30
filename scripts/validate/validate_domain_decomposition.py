#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Validate DocMirror structure-domain decomposition state."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "docmirror" / "configs" / "architecture" / "domain_decomposition.yaml"
OPTIONAL_MODULES = {
    "cv2",
    "fitz",
    "google.generativeai",
    "numpy",
    "onnxruntime",
    "openai",
    "pdfplumber",
    "rapidocr_onnxruntime",
}


def _load_manifest() -> dict[str, Any]:
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


def _module_from_path(path: Path) -> str:
    rel = path.relative_to(REPO_ROOT).with_suffix("")
    return ".".join(rel.parts)


def _path_exists(rel: str) -> bool:
    return (REPO_ROOT / rel).exists()


def _is_shim_file(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return "Compatibility shim" in text or "__path__" in text or "import_module" in text


def _target_has_moved_logic(target_rel: str) -> bool:
    target = REPO_ROOT / target_rel
    if not target.exists():
        return False
    if target.is_file():
        return True
    py_files = [path for path in target.rglob("*.py") if "__pycache__" not in path.parts]
    return any(path.name != "__init__.py" for path in py_files)


def validate_manifest_paths(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for name, domain in (manifest.get("canonical_domains") or {}).items():
        target = domain["target_path"]
        if not _path_exists(target):
            errors.append(f"{name}: missing target path {target}")
        for old_path in domain.get("old_paths") or []:
            if not old_path.startswith("docmirror/structure"):
                errors.append(f"{name}: old path must live under docmirror/structure: {old_path}")
    return errors


def validate_compatibility_shims(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    compatibility = manifest.get("compatibility") or {}
    if compatibility.get("status") == "removed":
        old_root = compatibility.get("old_root")
        if old_root and (REPO_ROOT / old_root).exists():
            errors.append(f"removed compatibility root still exists: {old_root}")
        return errors
    for name, domain in (manifest.get("canonical_domains") or {}).items():
        if not domain.get("moved", False):
            continue
        if not _target_has_moved_logic(domain["target_path"]):
            continue
        for old_path in domain.get("old_paths") or []:
            path = REPO_ROOT / old_path
            if not path.exists():
                errors.append(f"{name}: missing compatibility path {old_path}")
                continue
            if path.is_file() and path.suffix == ".py" and not _is_shim_file(path):
                errors.append(f"{name}: compatibility file is not a shim: {old_path}")
            if path.is_dir() and not _is_shim_file(path / "__init__.py"):
                errors.append(f"{name}: compatibility package lacks shim __init__.py: {old_path}")
    return errors


def _top_level_imports(path: Path) -> list[tuple[str, int]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []
    imports: list[tuple[str, int]] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append((node.module or "", node.lineno))
    return imports


def _matches_optional(module: str) -> bool:
    return any(module == item or module.startswith(f"{item}.") for item in OPTIONAL_MODULES)


def validate_optional_imports(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for name, domain in (manifest.get("canonical_domains") or {}).items():
        target = REPO_ROOT / domain["target_path"]
        if not target.exists():
            continue
        for path in target.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            for module, line in _top_level_imports(path):
                if _matches_optional(module):
                    rel = path.relative_to(REPO_ROOT)
                    errors.append(f"{name}: top-level optional import {module!r} at {rel}:{line}")
    return errors


def _is_exempt(rel: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, pattern) for pattern in patterns)


def validate_strict_new_imports(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    strict = manifest.get("strict_new_imports") or {}
    exempt = strict.get("exempt_paths") or []
    old_prefixes: list[str] = []
    for domain in (manifest.get("canonical_domains") or {}).values():
        if not domain.get("moved", False):
            continue
        for old_path in domain.get("old_paths") or []:
            if old_path.endswith(".py"):
                old_path = old_path[:-3]
            old_prefixes.append(old_path.replace("/", "."))
    old_prefix_tuple = tuple(sorted(old_prefixes, key=len, reverse=True))
    for path in (REPO_ROOT / "docmirror").rglob("*.py"):
        rel = str(path.relative_to(REPO_ROOT))
        if _is_exempt(rel, exempt):
            continue
        for module, line in _top_level_imports(path):
            if module.startswith(old_prefix_tuple):
                errors.append(f"new code imports old structure path at {rel}:{line}: {module}")
    return errors


def build_report(manifest: dict[str, Any], *, strict_new_imports: bool) -> dict[str, Any]:
    checks = {
        "manifest_paths": validate_manifest_paths(manifest),
        "compatibility_shims": validate_compatibility_shims(manifest),
        "optional_imports": validate_optional_imports(manifest),
    }
    if strict_new_imports:
        checks["strict_new_imports"] = validate_strict_new_imports(manifest)
    return {
        "manifest": str(MANIFEST_PATH.relative_to(REPO_ROOT)),
        "strict_new_imports": strict_new_imports,
        "checks": checks,
        "ok": not any(checks.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict-new-imports", action="store_true")
    parser.add_argument("--json", type=Path, help="Write machine-readable report")
    args = parser.parse_args()

    manifest = _load_manifest()
    report = build_report(manifest, strict_new_imports=args.strict_new_imports)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if report["ok"]:
        print("Domain decomposition validation OK")
        return 0

    print("Domain decomposition validation FAILED:", file=sys.stderr)
    for check_name, errors in report["checks"].items():
        for error in errors:
            print(f"  - [{check_name}] {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
