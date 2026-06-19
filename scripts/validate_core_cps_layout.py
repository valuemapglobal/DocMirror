#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Validate CPA CPS directory layout (design 12 §6 Phase 5)."""

from __future__ import annotations

import sys
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "docmirror" / "core"

REQUIRED_TOP_DIRS = [
    ("docmirror/core/entry", CORE / "entry"),
    ("docmirror/core/bridge", CORE / "bridge"),
    ("docmirror/core/physical", CORE / "physical"),
    ("docmirror/core/pipeline", CORE / "pipeline"),
    ("docmirror/core/analyze", CORE / "analyze"),
    ("docmirror/core/profile", CORE / "profile"),
    ("docmirror/core/segment", CORE / "segment"),
    ("docmirror/core/extract", CORE / "extract"),
    ("docmirror/core/table/pipeline", CORE / "table" / "pipeline"),
    ("docmirror/core/table/access", CORE / "table" / "access"),
    ("docmirror/core/table/compose", CORE / "table" / "compose"),
    ("docmirror/core/table/merge", CORE / "table" / "merge"),
    ("docmirror/core/ocr/postprocess", CORE / "ocr" / "postprocess"),
    ("docmirror/core/ocr/preprocess", CORE / "ocr" / "preprocess"),
    ("docmirror/core/ocr/recognize", CORE / "ocr" / "recognize"),
    ("docmirror/core/ocr/reconstruct", CORE / "ocr" / "reconstruct"),
    ("docmirror/core/scene", CORE / "scene"),
    ("docmirror/eval", ROOT / "docmirror" / "eval"),
    ("docmirror/features", ROOT / "docmirror" / "features"),
]

REQUIRED_FILES = [
    "entry/factory.py",
    "entry/perceive_result.py",
    "bridge/parse_result_bridge.py",
    "pipeline/document_pipeline.py",
    "pipeline/page_pipeline.py",
    "pipeline/page_extractor.py",
    "pipeline/pdf_processor.py",
    "pipeline/page_worker.py",
    "analyze/pre_analyzer.py",
    "analyze/conservation.py",
    "profile/registry.py",
    "segment/zones.py",
    "extract/engine.py",
    "table/pipeline/stage_header.py",
    "table/pipeline/stage_preamble.py",
    "table/pipeline/stage_structure.py",
    "table/pipeline/stage_domain.py",
    "table/pipeline/hooks/generic.py",
    "table/pipeline/hooks/ledger_borderless.py",
    "segment/graph_router.py",
    "segment/layout_model.py",
    "table/access/__init__.py",
    "table/compose/composer.py",
    "table/merge/merger.py",
    "pipeline/stages/page_finalize.py",
    "ocr/pipeline.py",
    "ocr/postprocess/generic.py",
    "scene/evidence_engine.py",
]

FORBIDDEN_IN_ZONES = ["def __getattr__", "_DEPRECATED_REEXPORTS"]

FORBIDDEN_STAGE_IMPORTS = {
    "pipeline": ("docmirror.core.bridge", "docmirror.adapters", "docmirror.framework.dispatcher"),
    "bridge": ("docmirror.adapters", "docmirror.framework.dispatcher"),
    "extract": ("docmirror.core.bridge",),
}


def _imports_in_file(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
    return out


def main() -> int:
    errors: list[str] = []
    for label, path in REQUIRED_TOP_DIRS:
        if not path.is_dir():
            errors.append(f"missing directory: {label}")
    for rel in REQUIRED_FILES:
        path = CORE / rel
        if not path.is_file():
            errors.append(f"missing file: {path.relative_to(ROOT)}")
    zones = CORE / "segment" / "zones.py"
    if zones.is_file():
        text = zones.read_text(encoding="utf-8")
        for token in FORBIDDEN_IN_ZONES:
            if token in text:
                errors.append(f"forbidden token {token!r} in {zones.relative_to(ROOT)}")
    for area, prefixes in FORBIDDEN_STAGE_IMPORTS.items():
        area_dir = CORE / area
        if not area_dir.is_dir():
            continue
        for path in area_dir.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            for imp in _imports_in_file(path):
                for prefix in prefixes:
                    if imp == prefix or imp.startswith(prefix + "."):
                        errors.append(
                            f"forbidden dependency {imp!r} in {path.relative_to(ROOT)}"
                        )
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print("CPA CPS layout OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
