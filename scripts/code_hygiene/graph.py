# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Import graph utilities for orphan-module detection."""

from __future__ import annotations

import ast
import os
import re
from collections import defaultdict
from pathlib import Path

from scripts.code_hygiene.config import CONFIGS_YAML, EXCLUDE_DIR_NAMES, ROOT, SCAN_PACKAGE_DIRS


def py_files(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    out: list[Path] = []
    for path in base.rglob("*.py"):
        if any(part in EXCLUDE_DIR_NAMES for part in path.parts):
            continue
        out.append(path)
    return sorted(out)


def module_name(path: Path, *, root: Path = ROOT) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = rel.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def path_for_module(mod: str, *, root: Path = ROOT) -> Path | None:
    candidate = root / Path(*mod.split("."))
    if candidate.with_suffix(".py").is_file():
        return candidate.with_suffix(".py")
    init = candidate / "__init__.py"
    if init.is_file():
        return init
    return None


def _relative_base_parts(source_mod: str, *, is_init: bool) -> list[str]:
    parts = source_mod.split(".")
    if not is_init:
        return parts[:-1]
    return parts


def resolved_imports_in_file(path: Path) -> list[str]:
    """Return absolute module paths referenced by imports in *path*."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    source_mod = module_name(path)
    is_init = path.name == "__init__.py"
    out: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append(alias.name)
            continue

        if not isinstance(node, ast.ImportFrom):
            continue

        if node.level == 0:
            if node.module:
                out.append(node.module)
                for alias in node.names:
                    if alias.name != "*":
                        out.append(f"{node.module}.{alias.name}")
            continue

        base = _relative_base_parts(source_mod, is_init=is_init)
        for _ in range(node.level - 1):
            if base:
                base.pop()

        if node.module:
            parts = base + node.module.split(".")
            out.append(".".join(parts))
        else:
            for alias in node.names:
                if alias.name != "*":
                    out.append(".".join([*base, alias.name]))

    return out


def importlib_literals_in_file(path: Path) -> list[str]:
    """Extract module strings passed to importlib.import_module / __import__."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        if name not in {"import_module", "__import__"}:
            continue
        if not node.args:
            continue
        arg0 = node.args[0]
        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
            out.append(arg0.value)
    return out


def patch_literals_in_file(path: Path) -> list[str]:
    """Extract module paths used by mock.patch / monkeypatch.setattr string targets."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        if name not in {"patch", "setattr"}:
            continue
        if not node.args:
            continue
        arg0 = node.args[0]
        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str) and arg0.value.startswith("docmirror."):
            out.append(arg0.value)
    return out


def yaml_config_module_refs() -> list[str]:
    """Collect docmirror module paths declared in YAML configs (FCR, MEP, plugins)."""
    refs: list[str] = []
    yaml_roots = (CONFIGS_YAML,)
    module_key = re.compile(r"^\s*module:\s*(docmirror\.[\w.]+)\s*$")
    adapter_key = re.compile(r"^\s*adapter:\s*(docmirror\.[\w.]+)\s*$")

    for base in yaml_roots:
        if not base.is_dir():
            continue
        for path in base.rglob("*.yaml"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                for pattern in (module_key, adapter_key):
                    m = pattern.match(line)
                    if m:
                        refs.append(m.group(1))

    schema_registry = ROOT / "docmirror" / "models" / "schemas" / "registry.yaml"
    if schema_registry.is_file():
        try:
            import yaml

            data = yaml.safe_load(schema_registry.read_text(encoding="utf-8")) or {}
            for module_key in (data.get("schemas") or {}).values():
                if module_key:
                    refs.append(f"docmirror.models.schemas.{module_key}")
        except Exception:
            pass

    return refs


def imports_in_file(path: Path) -> list[str]:
    """Backward-compatible alias — prefer ``resolved_imports_in_file``."""
    return resolved_imports_in_file(path)


def package_modules() -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for base in SCAN_PACKAGE_DIRS:
        for path in py_files(base):
            modules[module_name(path)] = path
    return modules


def inbound_reference_counts(
    modules: dict[str, Path] | None = None,
    *,
    scan_roots: tuple[Path, ...] | None = None,
) -> dict[str, int]:
    """Count how many files import each module (approximate static analysis)."""
    modules = modules or package_modules()
    mod_set = set(modules)
    counts: dict[str, int] = defaultdict(int)
    roots = scan_roots or (ROOT / "docmirror", ROOT / "scripts", ROOT / "tests", ROOT / "tools")

    def _bump(target: str) -> None:
        if target in mod_set:
            counts[target] += 1
            return
        parts = target.split(".")
        for i in range(len(parts), 0, -1):
            parent = ".".join(parts[:i])
            if parent in mod_set:
                counts[parent] += 1
                return

    for base in roots:
        if not base.is_dir():
            continue
        for path in py_files(base):
            for imp in resolved_imports_in_file(path):
                _bump(imp)
            for imp in importlib_literals_in_file(path):
                _bump(imp)
            for imp in patch_literals_in_file(path):
                _bump(imp)

    for ref in yaml_config_module_refs():
        _bump(ref)

    return dict(counts)


def string_references_in_repo(needle: str, *, search_roots: tuple[Path, ...] | None = None) -> int:
    """Count non-Python text references (docs, yaml, ci)."""
    roots = search_roots or (ROOT,)
    total = 0
    extensions = {".py", ".md", ".yaml", ".yml", ".toml", ".json", ".sh"}
    for base in roots:
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [
                name
                for name in dirnames
                if name not in EXCLUDE_DIR_NAMES
                and name
                not in {
                    ".deepseek",
                    ".ruff_cache",
                    ".mypy_cache",
                    "artifacts",
                    "build",
                    "dist",
                    "docmirror_enterprise",
                    "docmirror_finance",
                    "output",
                    "reports",
                }
            ]
            current = Path(dirpath)
            if any(part in EXCLUDE_DIR_NAMES for part in current.parts):
                continue
            for filename in filenames:
                path = current / filename
                if path.suffix not in extensions:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if needle in text:
                    total += 1
    return total
