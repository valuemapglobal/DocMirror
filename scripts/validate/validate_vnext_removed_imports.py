#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Gate new production imports of removed page projection modules."""

from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCMIRROR = REPO_ROOT / "docmirror"
BASELINE_PATH = REPO_ROOT / "docmirror" / "configs" / "architecture" / "vnext_removed_import_baseline.yaml"

REMOVED_PAGE_PROJECTION_IMPORT = ".".join(("docmirror", "ocr", "page_" + "canvas"))
REMOVED_PROJECT_IMPORT = ".".join(("docmirror", "models", "mirror", "leg" + "acy_" + "project"))

FORBIDDEN_PREFIXES = (
    REMOVED_PAGE_PROJECTION_IMPORT,
    REMOVED_PROJECT_IMPORT,
)

# Existing migration allowlist. New production imports should target vNext
# evidence/topology/layout/quality access layers instead of these modules.
ALLOWED_IMPORTERS = {
    "docmirror.evidence.plane",
    "docmirror.evidence.structure_provenance",
    "docmirror.eval.tqg.runner",
    "docmirror.input.bridge.parse_result_bridge",
    "docmirror.models.entities.parse_result",
    "docmirror.models.mirror.block_fields",
    "docmirror.models.mirror.domain_access",
    "docmirror.ocr.aistudio_provider",
    "docmirror.ocr.fallback",
    "docmirror.ocr.local_structure.build",
    "docmirror.ocr.local_structure.candidate_supplement",
    "docmirror.ocr.micro_grid.models",
    "docmirror.ocr.preprocess",
    "docmirror.ocr.recognize",
    "docmirror.ocr.reconstruct",
    "docmirror.ocr.scanned.analyze_page",
    "docmirror.ocr.scanned.universal",
    "docmirror.ocr.vision.rapidocr_engine",
    "docmirror.plugins._base.generic_mirror_adapter",
    "docmirror.plugins._base.kv_community_enrich",
    "docmirror.topology.page",
}


def module_name(path: Path) -> str:
    rel = path.relative_to(REPO_ROOT).with_suffix("")
    parts = rel.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def iter_py_files(root: Path = DOCMIRROR) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def imported_modules(path: Path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((node.lineno, alias.name))
            continue
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.append((node.lineno, node.module))
    return out


def is_forbidden_import(imported: str) -> bool:
    return any(imported == prefix or imported.startswith(f"{prefix}.") for prefix in FORBIDDEN_PREFIXES)


def is_allowed_importer(importer: str, imported: str) -> bool:
    if imported.startswith(REMOVED_PAGE_PROJECTION_IMPORT) and importer.startswith(REMOVED_PAGE_PROJECTION_IMPORT):
        return True
    return importer in ALLOWED_IMPORTERS


def check(root: Path = DOCMIRROR) -> list[str]:
    errors: list[str] = []
    for path in iter_py_files(root):
        importer = module_name(path)
        for lineno, imported in imported_modules(path):
            if not is_forbidden_import(imported):
                continue
            if is_allowed_importer(importer, imported):
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            errors.append(f"{rel}:{lineno}: {importer} imports removed module {imported}")
    return errors


def usage_counts(root: Path = DOCMIRROR) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for path in iter_py_files(root):
        for _lineno, imported in imported_modules(path):
            for prefix in FORBIDDEN_PREFIXES:
                if imported == prefix or imported.startswith(f"{prefix}."):
                    counts[prefix] += 1
                    break
    return {prefix: counts.get(prefix, 0) for prefix in FORBIDDEN_PREFIXES}


def validate_baseline(root: Path = DOCMIRROR, baseline_path: Path = BASELINE_PATH) -> list[str]:
    if not baseline_path.is_file():
        return [f"missing vNext raw import baseline: {baseline_path.relative_to(REPO_ROOT).as_posix()}"]
    data = yaml.safe_load(baseline_path.read_text(encoding="utf-8")) or {}
    removed_imports = _baseline_entries(data.get("removed_imports") or {})
    counts = usage_counts(root)
    errors: list[str] = []
    for prefix in FORBIDDEN_PREFIXES:
        item = removed_imports.get(prefix)
        if not isinstance(item, dict):
            errors.append(f"baseline missing entry for {prefix}")
            continue
        max_count = int(item.get("max_import_count", -1))
        actual = counts.get(prefix, 0)
        if actual > max_count:
            errors.append(f"{prefix}: import count {actual} exceeds baseline max {max_count}")
    return errors


def _baseline_entries(raw: object) -> dict[str, dict]:
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items() if isinstance(value, dict)}
    if not isinstance(raw, list):
        return {}
    out: dict[str, dict] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        module = item.get("module")
        if not module and isinstance(item.get("module_parts"), list):
            module = ".".join(_module_part(part) for part in item["module_parts"])
        if module:
            out[str(module)] = item
    return out


def _module_part(part: object) -> str:
    if isinstance(part, list):
        return "".join(str(piece) for piece in part)
    return str(part)


def main() -> int:
    errors = check() + validate_baseline()
    if errors:
        print("vNext removed import gate FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print(
            "New production code must use vNext evidence/topology/layout/quality access layers. "
            "If an existing raw dependency is still required, document it in "
            "the internal page projection unification plan and add a temporary allowlist entry.",
            file=sys.stderr,
        )
        return 1
    counts = usage_counts()
    counts_text = ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
    print(f"vNext removed import gate OK ({counts_text})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
