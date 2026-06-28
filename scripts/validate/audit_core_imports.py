#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Audit DocMirror architecture import graph."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DM = "docmirror"
LEGACY_CORE_IMPORT = f"{DM}.core"
CORE = ROOT / DM / "core"
INPUT = ROOT / DM / "input"
STRUCTURE = ROOT / DM / "structure"
PLUGINS = ROOT / DM / "plugins"

FORBIDDEN_FOR_PLUGINS = {
    "docmirror.input.extraction.extractor",
    "docmirror.layout.segment.zones",
    "docmirror.ocr.fallback",
}

FORBIDDEN_CORE_IMPORT_PREFIXES = {
    "docmirror.plugins": "core_must_not_depend_on_plugins",
    "docmirror.server": "core_must_not_depend_on_server",
}

FORBIDDEN_MODELS_IMPORT_PREFIXES = {
    LEGACY_CORE_IMPORT: "models_must_not_depend_on_core",
    "docmirror.framework": "models_must_not_depend_on_framework",
    "docmirror.input.adapters": "models_must_not_depend_on_adapters",
}

FORBIDDEN_BRIDGE_IMPORT_PREFIXES = {
    "docmirror.input.adapters": "bridge_must_not_call_adapters",
    "docmirror.framework.dispatcher": "bridge_must_not_call_dispatcher",
}

LAZY_HUB_FILE = STRUCTURE / "segment" / "zones.py"
LAZY_HUB_MARKERS = ("def __getattr__", "_DEPRECATED_REEXPORTS")
GOD_FILE_LOC = 800


def _py_files(base: Path) -> list[Path]:
    return [p for p in base.rglob("*.py") if "__pycache__" not in p.parts]


def _module_name(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    return ".".join(rel.parts)


def _imports_in_file(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
    return out


def layout_analysis_consumers() -> dict[str, list[str]]:
    pattern = re.compile(r"layout_analysis")
    consumers: dict[str, list[str]] = defaultdict(list)
    for path in _py_files(ROOT):
        if "docmirror" not in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if pattern.search(text):
            mod = _module_name(path)
            for line in text.splitlines():
                if "layout_analysis" in line and ("import" in line):
                    consumers[mod].append(line.strip())
    return dict(consumers)


def plugin_forbidden_imports() -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    for path in _py_files(PLUGINS):
        for imp in _imports_in_file(path):
            for forbidden in FORBIDDEN_FOR_PLUGINS:
                if imp == forbidden or imp.startswith(forbidden + "."):
                    violations.append({"file": str(path.relative_to(ROOT)), "import": imp, "forbidden": forbidden})
    return violations


def efmp_boundary_violations() -> list[dict[str, str]]:
    """Report EFMP evidence/hypothesis and projection boundary violations."""
    violations: list[dict[str, str]] = []
    models = ROOT / "docmirror" / "models"
    bridge = INPUT / "bridge"

    for path in _py_files(CORE):
        for imp in _imports_in_file(path):
            for prefix, rule in FORBIDDEN_CORE_IMPORT_PREFIXES.items():
                if imp == prefix or imp.startswith(prefix + "."):
                    violations.append({"file": str(path.relative_to(ROOT)), "import": imp, "rule": rule})

    for path in _py_files(models):
        for imp in _imports_in_file(path):
            for prefix, rule in FORBIDDEN_MODELS_IMPORT_PREFIXES.items():
                if imp == prefix or imp.startswith(prefix + "."):
                    violations.append({"file": str(path.relative_to(ROOT)), "import": imp, "rule": rule})

    for path in _py_files(bridge):
        for imp in _imports_in_file(path):
            for prefix, rule in FORBIDDEN_BRIDGE_IMPORT_PREFIXES.items():
                if imp == prefix or imp.startswith(prefix + "."):
                    violations.append({"file": str(path.relative_to(ROOT)), "import": imp, "rule": rule})

    return violations


def inbound_reference_counts() -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    core_modules = {_module_name(p): p for p in _py_files(CORE)}
    for path in _py_files(ROOT):
        if path.is_relative_to(CORE) and path.suffix == ".py":
            continue
        for imp in _imports_in_file(path):
            for mod in core_modules:
                if imp == mod or imp.startswith(mod + "."):
                    counts[mod] += 1
    # internal core refs
    for path in _py_files(CORE):
        src = _module_name(path)
        for imp in _imports_in_file(path):
            for mod in core_modules:
                if mod == src:
                    continue
                if imp == mod or imp.startswith(mod + "."):
                    counts[mod] += 1
    return dict(counts)


def god_files() -> list[dict[str, int]]:
    rows: list[dict[str, int]] = []
    for path in _py_files(CORE):
        n = sum(1 for _ in path.open(encoding="utf-8"))
        if n > GOD_FILE_LOC:
            rows.append({"module": _module_name(path), "lines": n})
    return sorted(rows, key=lambda r: -r["lines"])


def lazy_hub_present() -> bool:
    if not LAZY_HUB_FILE.is_file():
        return False
    text = LAZY_HUB_FILE.read_text(encoding="utf-8")
    return any(marker in text for marker in LAZY_HUB_MARKERS)


def run_audit() -> dict:
    refs = inbound_reference_counts()
    dead = [m for m, c in refs.items() if c == 0 and m.startswith(LEGACY_CORE_IMPORT)]
    return {
        "layout_analysis_consumers": layout_analysis_consumers(),
        "plugin_forbidden_imports": plugin_forbidden_imports(),
        "efmp_boundary_violations": efmp_boundary_violations(),
        "zero_inbound_core_modules": sorted(dead),
        "god_files_over_800_loc": god_files(),
        "lazy_hub_present": lazy_hub_present(),
    }


def audit_failures(data: dict) -> list[str]:
    """Human-readable failure messages (mirrors CI assertions)."""
    failures: list[str] = []
    if data.get("plugin_forbidden_imports"):
        failures.append(f"plugin_forbidden_imports: {data['plugin_forbidden_imports']}")
    if data.get("efmp_boundary_violations"):
        failures.append(f"efmp_boundary_violations: {data['efmp_boundary_violations']}")
    if data.get("lazy_hub_present"):
        failures.append("lazy_hub_present: segment/zones.py still exposes deprecated re-exports")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit DocMirror architecture imports")
    parser.add_argument("--json", type=Path, help="Write JSON report to path")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when plugin import or lazy-hub violations are present",
    )
    args = parser.parse_args()
    report = run_audit()
    failures = audit_failures(report)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {args.json}")
    elif not args.strict:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.strict and failures:
        for msg in failures:
            print(msg, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
