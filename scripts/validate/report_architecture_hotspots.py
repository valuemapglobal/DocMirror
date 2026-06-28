#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Report architecture hotspots without destabilizing the release gate."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "docmirror" / "configs" / "architecture" / "hotspot_manifest.yaml"


def _load_config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _py_files() -> list[Path]:
    ignored = {".git", ".venv", "venv", "__pycache__", "build", "dist"}
    files = []
    for path in (REPO_ROOT / "docmirror").rglob("*.py"):
        if ignored.intersection(path.parts):
            continue
        files.append(path)
    return sorted(files)


def _line_count(path: Path) -> int:
    return sum(1 for _ in path.open(encoding="utf-8", errors="replace"))


def _node_end_lineno(node: ast.AST) -> int:
    return int(getattr(node, "end_lineno", getattr(node, "lineno", 0)) or 0)


def _function_hotspots(path: Path) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [{"path": str(path.relative_to(REPO_ROOT)), "name": "<syntax-error>", "lines": 0, "error": str(exc)}]

    hotspots: list[dict[str, Any]] = []
    parents: list[str] = []

    def visit(node: ast.AST) -> None:
        is_function = isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        is_class = isinstance(node, ast.ClassDef)
        if is_class:
            parents.append(node.name)
        if is_function:
            start = int(getattr(node, "lineno", 0) or 0)
            end = _node_end_lineno(node)
            qualname = ".".join([*parents, node.name])
            hotspots.append(
                {
                    "path": str(path.relative_to(REPO_ROOT)),
                    "name": qualname,
                    "lines": max(0, end - start + 1),
                    "start": start,
                }
            )
            parents.append(node.name)
        for child in ast.iter_child_nodes(node):
            visit(child)
        if is_function or is_class:
            parents.pop()

    visit(tree)
    return hotspots


def _import_name(node: ast.Import | ast.ImportFrom) -> str:
    if isinstance(node, ast.Import):
        return node.names[0].name
    return node.module or ""


def _matches_optional(module: str, optional_modules: list[str]) -> str | None:
    for optional in optional_modules:
        if module == optional or module.startswith(f"{optional}."):
            return optional
    return None


def _top_level_optional_imports(path: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []

    rel = str(path.relative_to(REPO_ROOT))
    allowed_prefixes = tuple(config.get("allowed_top_level_optional_import_prefixes") or [])
    if rel.startswith(allowed_prefixes):
        return []

    optional_modules = config.get("optional_modules") or []
    leaks: list[dict[str, Any]] = []
    for node in tree.body:
        if not isinstance(node, ast.Import | ast.ImportFrom):
            continue
        module = _import_name(node)
        optional = _matches_optional(module, optional_modules)
        if optional:
            leaks.append({"path": rel, "module": module, "optional": optional, "line": node.lineno})
    return leaks


def build_report() -> dict[str, Any]:
    config = _load_config()
    thresholds = config.get("thresholds") or {}
    top_n = config.get("top_n") or {}

    files = [{"path": str(path.relative_to(REPO_ROOT)), "lines": _line_count(path)} for path in _py_files()]
    functions = [item for path in _py_files() for item in _function_hotspots(path)]
    optional_imports = [item for path in _py_files() for item in _top_level_optional_imports(path, config)]

    files.sort(key=lambda item: item["lines"], reverse=True)
    functions.sort(key=lambda item: item["lines"], reverse=True)

    return {
        "thresholds": thresholds,
        "largest_files": files[: int(top_n.get("files", 12))],
        "largest_functions": functions[: int(top_n.get("functions", 20))],
        "large_file_warnings": [
            item for item in files if item["lines"] > int(thresholds.get("large_file_warn_lines", 1500))
        ],
        "large_function_warnings": [
            item for item in functions if item["lines"] > int(thresholds.get("large_function_warn_lines", 250))
        ],
        "top_level_optional_import_warnings": optional_imports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="Write machine-readable report JSON")
    parser.add_argument("--fail-optional-leaks", action="store_true", help="Fail on top-level optional import warnings")
    args = parser.parse_args()

    report = build_report()
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        "Architecture hotspot report: "
        f"large_files={len(report['large_file_warnings'])} "
        f"large_functions={len(report['large_function_warnings'])} "
        f"optional_import_warnings={len(report['top_level_optional_import_warnings'])}"
    )
    for item in report["largest_files"][:5]:
        print(f"  file {item['path']} lines={item['lines']}")
    for item in report["largest_functions"][:5]:
        print(f"  function {item['path']}:{item.get('start', 0)} {item['name']} lines={item['lines']}")

    if args.fail_optional_leaks and report["top_level_optional_import_warnings"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
