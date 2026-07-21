#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Validate the post-restructure DocMirror directory layout."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCMIRROR = ROOT / "docmirror"
DM = "docmirror"
CORE_IMPORT = f"{DM}.core"

EXPECTED_TOP_LEVEL_DIRS = {
    "cli",
    "configs",
    "domains",
    "errors",
    "eval",
    "evidence",
    "features",
    "framework",
    "geometry",
    "input",
    "layout",
    "models",
    "ocr",
    "output",
    "plugins",
    "quality",
    "runtime",
    "sdk",
    "security",
    "server",
    "tables",
    "topology",
}

REQUIRED_DIRS = [
    DOCMIRROR / "input",
    DOCMIRROR / "input" / "adapters",
    DOCMIRROR / "input" / "canonical",
    DOCMIRROR / "input" / "extraction",
    DOCMIRROR / "input" / "pipeline",
    DOCMIRROR / "geometry",
    DOCMIRROR / "geometry" / "verification",
    DOCMIRROR / "layout",
    DOCMIRROR / "layout" / "normalization",
    DOCMIRROR / "layout" / "profile",
    DOCMIRROR / "layout" / "scene",
    DOCMIRROR / "layout" / "segment",
    DOCMIRROR / "ocr",
    DOCMIRROR / "ocr" / "local_structure",
    DOCMIRROR / "ocr" / "micro_grid",
    DOCMIRROR / "domains",
    DOCMIRROR / "tables",
    DOCMIRROR / "topology",
    DOCMIRROR / "topology" / "region_graph",
    DOCMIRROR / "topology" / "relations",
    DOCMIRROR / "topology" / "resolution",
    DOCMIRROR / "output",
    DOCMIRROR / "output" / "debug",
    DOCMIRROR / "runtime",
    DOCMIRROR / "framework",
    DOCMIRROR / "framework" / "di",
    DOCMIRROR / "framework" / "middlewares",
    DOCMIRROR / "evidence",
    DOCMIRROR / "quality",
    DOCMIRROR / "features",
    DOCMIRROR / "features" / "rag",
    DOCMIRROR / "sdk",
    DOCMIRROR / "sdk" / "integration",
]

REQUIRED_FILES = [
    DOCMIRROR / "input" / "pipeline" / "__init__.py",
    DOCMIRROR / "input" / "canonical" / "assembler.py",
    DOCMIRROR / "input" / "canonical" / "page_assembler.py",
    DOCMIRROR / "input" / "extraction" / "extractor.py",
    DOCMIRROR / "tables" / "engine.py",
    DOCMIRROR / "tables" / "cross_page_fusion.py",
    DOCMIRROR / "ocr" / "pipeline.py",
    DOCMIRROR / "evidence" / "plane.py",
    DOCMIRROR / "topology" / "page.py",
    DOCMIRROR / "topology" / "reconstructors.py",
    DOCMIRROR / "output" / "dmir.py",
    DOCMIRROR / "output" / "mirror_vnext_projection.py",
    DOCMIRROR / "runtime" / "progress_bus.py",
    DOCMIRROR / "runtime" / "control.py",
    DOCMIRROR / "framework" / "extension_points.py",
    DOCMIRROR / "errors" / "result.py",
    DOCMIRROR / "framework" / "di" / "container.py",
    DOCMIRROR / "framework" / "middlewares" / "base.py",
]

REMOVED_PATHS = [
    DOCMIRROR / "adapters",
    DOCMIRROR / "core",
    DOCMIRROR / "di",
    DOCMIRROR / "middlewares",
    DOCMIRROR / "integration",
    DOCMIRROR / "rag",
    DOCMIRROR / "sdk.py",
    DOCMIRROR / "edition_facade.py",
    DOCMIRROR / "input" / "pipeline" / "raw",
    DOCMIRROR / "input" / "bridge",
    DOCMIRROR / "server" / "output_plan.py",
    DOCMIRROR / "server" / "projection_dag.py",
    DOCMIRROR / "server" / "projection_visualizer.py",
    DOCMIRROR / "server" / "output_selection.py",
    DOCMIRROR / "configs" / "output_profile.py",
    DOCMIRROR / "runtime" / "profiles.py",
    DOCMIRROR / "framework" / "edition_defaults.py",
    DOCMIRROR / "framework" / "delivery_contract.py",
    DOCMIRROR / "framework" / "cache.py",
    DOCMIRROR / "framework" / "execution_fingerprint.py",
    DOCMIRROR / "server" / "edition_access.py",
    DOCMIRROR / "models" / "semantic_store.py",
    DOCMIRROR / "topology" / "document_graph.py",
    DOCMIRROR / "domains" / "registry.py",
    DOCMIRROR / "errors" / "envelope.py",
    DOCMIRROR / "cli" / "explainability_commands.py",
    DOCMIRROR / "ocr" / "correction" / "report.py",
    DOCMIRROR / "structure",
    DOCMIRROR / "structure" / "tables" / "merge",
    DOCMIRROR / "core" / "analyze",
    DOCMIRROR / "core" / "bridge",
    DOCMIRROR / "core" / "debug",
    DOCMIRROR / "core" / "extract",
    DOCMIRROR / "core" / "extraction",
    DOCMIRROR / "core" / "geometry",
    DOCMIRROR / "core" / "ocr",
    DOCMIRROR / "core" / "output",
    DOCMIRROR / "core" / "physical",
    DOCMIRROR / "core" / "pipeline",
    DOCMIRROR / "core" / "profile",
    DOCMIRROR / "core" / "resolution",
    DOCMIRROR / "core" / "scene",
    DOCMIRROR / "core" / "segment",
    DOCMIRROR / "core" / "structure",
    DOCMIRROR / "core" / "table",
    DOCMIRROR / "core" / "utils",
    DOCMIRROR / "core" / "extension_points.py",
    DOCMIRROR / "core" / "result.py",
    DOCMIRROR / "core" / "mirror_core_vnext.py",
    ROOT / "input",
    ROOT / "structure",
    ROOT / "docmirror-bak",
]

FORBIDDEN_IMPORT_PREFIXES = (
    f"{DM}.adapters",
    f"{DM}.di",
    f"{DM}.middlewares",
    f"{DM}.integration",
    f"{DM}.rag",
    f"{DM}.structure",
    CORE_IMPORT,
    f"{CORE_IMPORT}.analyze",
    f"{CORE_IMPORT}.bridge",
    f"{CORE_IMPORT}.debug",
    f"{CORE_IMPORT}.extract",
    f"{CORE_IMPORT}.extraction",
    f"{CORE_IMPORT}.geometry",
    f"{CORE_IMPORT}.ocr",
    f"{CORE_IMPORT}.output",
    f"{CORE_IMPORT}.physical",
    f"{CORE_IMPORT}.pipeline",
    f"{CORE_IMPORT}.profile",
    f"{CORE_IMPORT}.resolution",
    f"{CORE_IMPORT}.scene",
    f"{CORE_IMPORT}.segment",
    f"{CORE_IMPORT}.structure",
    f"{CORE_IMPORT}.table",
    f"{CORE_IMPORT}.utils",
    f"{CORE_IMPORT}.extension_points",
    f"{CORE_IMPORT}.result",
    f"{CORE_IMPORT}.mirror_core_vnext",
)


def _py_files(base: Path) -> list[Path]:
    return [p for p in base.rglob("*.py") if "__pycache__" not in p.parts]


def _imports_in_file(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def main() -> int:
    errors: list[str] = []
    actual_top_level_dirs = {p.name for p in DOCMIRROR.iterdir() if p.is_dir() and p.name != "__pycache__"}
    unexpected = sorted(actual_top_level_dirs - EXPECTED_TOP_LEVEL_DIRS)
    missing = sorted(EXPECTED_TOP_LEVEL_DIRS - actual_top_level_dirs)
    for name in unexpected:
        errors.append(f"unexpected top-level directory: docmirror/{name}")
    for name in missing:
        errors.append(f"missing top-level directory: docmirror/{name}")
    for path in REQUIRED_DIRS:
        if not path.is_dir():
            errors.append(f"missing directory: {path.relative_to(ROOT)}")
    for path in REQUIRED_FILES:
        if not path.is_file():
            errors.append(f"missing file: {path.relative_to(ROOT)}")
    for path in REMOVED_PATHS:
        if path.exists():
            errors.append(f"removed path still exists: {path.relative_to(ROOT)}")

    for path in _py_files(DOCMIRROR) + _py_files(ROOT / "tests") + _py_files(ROOT / "scripts"):
        for imp in _imports_in_file(path):
            for prefix in FORBIDDEN_IMPORT_PREFIXES:
                if imp == prefix or imp.startswith(prefix + "."):
                    errors.append(f"forbidden import in {path.relative_to(ROOT)}: {imp}")

    if errors:
        print("Layout validation FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("Layout validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
