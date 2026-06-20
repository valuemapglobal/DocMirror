# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Individual hygiene checkers."""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

from scripts.code_hygiene.allowlist import is_allowed, load_allowlist
from scripts.code_hygiene.config import (
    CONFIGS_YAML,
    ENTRY_MODULE_PATHS,
    ENTRY_MODULE_SUFFIXES,
    EXCLUDE_DIR_NAMES,
    ORPHAN_EXCLUDE_PATH_PARTS,
    ROOT,
    RUFF_HYGIENE_SELECT,
    RUFF_PER_FILE_IGNORES,
    RUFF_TARGETS,
    SCRIPTS,
    TOOLS,
)
from scripts.code_hygiene.graph import (
    inbound_reference_counts,
    package_modules,
    py_files,
    string_references_in_repo,
)
from scripts.code_hygiene.models import Category, CheckResult, Finding, Severity

_RUFF_CODE_CATEGORY = {
    "F401": Category.UNUSED_IMPORT,
    "F841": Category.UNUSED_VARIABLE,
    "ARG001": Category.UNUSED_ARGUMENT,
    "ARG002": Category.UNUSED_ARGUMENT,
    "ARG005": Category.UNUSED_ARGUMENT,
    "ERA001": Category.COMMENTED_CODE,
}


def check_ruff_strict(allowlist: dict | None = None) -> CheckResult:
    """Run Ruff with hygiene-focused rules (imports, args, commented code, UP)."""
    allowlist = allowlist or load_allowlist()
    t0 = time.perf_counter()
    result = CheckResult(name="ruff_strict")
    if shutil.which("ruff") is None:
        result.skipped = True
        result.skip_reason = "ruff not installed"
        return result

    select = ",".join(RUFF_HYGIENE_SELECT)
    cmd = ["ruff", "check", *RUFF_TARGETS, "--select", select, "--output-format", "json"]
    for pattern, codes in RUFF_PER_FILE_IGNORES.items():
        for code in codes:
            cmd.extend(["--per-file-ignores", f"{pattern}:{code}"])

    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    result.duration_ms = int((time.perf_counter() - t0) * 1000)

    if proc.returncode not in (0, 1):
        result.skipped = True
        result.skip_reason = proc.stderr.strip() or f"ruff exited {proc.returncode}"
        return result

    import json

    try:
        items = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        result.skipped = True
        result.skip_reason = "invalid ruff json output"
        return result

    for item in items:
        code = str(item.get("code", ""))
        loc = item.get("location", {}) or {}
        filename = str(item.get("filename", ""))
        line = loc.get("row", 0)
        message = str(item.get("message", ""))
        category = _RUFF_CODE_CATEGORY.get(
            code, Category.DEPRECATED_SYNTAX if code.startswith("UP") else Category.UNUSED_VARIABLE
        )
        key = f"{filename}:{line}:{code}"
        if is_allowed("ruff", key, allowlist) or is_allowed(category.value, filename, allowlist):
            continue
        result.findings.append(
            Finding(
                category=category,
                severity=Severity.WARNING if code.startswith("UP") else Severity.ERROR,
                message=message,
                location=f"{filename}:{line}",
                symbol=code,
                checker="ruff_strict",
                hint="Remove unused symbol or add to configs/hygiene/allowlist.yaml",
            )
        )
    return result


def check_vulture(allowlist: dict | None = None, *, min_confidence: int = 80) -> CheckResult:
    """Dead functions/classes via vulture (optional dev dependency)."""
    allowlist = allowlist or load_allowlist()
    t0 = time.perf_counter()
    result = CheckResult(name="vulture")
    if shutil.which("vulture") is None:
        result.skipped = True
        result.skip_reason = "vulture not installed (pip install vulture)"
        return result

    paths = [str(ROOT / t) for t in RUFF_TARGETS]
    proc = subprocess.run(
        ["vulture", *paths, f"--min-confidence={min_confidence}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    result.duration_ms = int((time.perf_counter() - t0) * 1000)

    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line or "unused" not in line.lower():
            continue
        # format: path:line: message (confidence%)
        m = re.match(r"^(.+?):(\d+):\s+(.+)$", line)
        if not m:
            continue
        path, lineno, msg = m.group(1), m.group(2), m.group(3)
        key = f"{path}:{lineno}"
        if is_allowed("vulture", key, allowlist) or is_allowed("vulture", path, allowlist):
            continue
        result.findings.append(
            Finding(
                category=Category.DEAD_CODE,
                severity=Severity.WARNING,
                message=msg,
                location=f"{path}:{lineno}",
                checker="vulture",
                hint="Confirm symbol is unused, then delete or whitelist",
            )
        )
    return result


def check_orphan_modules(allowlist: dict | None = None) -> CheckResult:
    """Modules under docmirror/ with zero static inbound imports."""
    allowlist = allowlist or load_allowlist()
    t0 = time.perf_counter()
    result = CheckResult(name="orphan_modules")
    modules = package_modules()
    counts = inbound_reference_counts(modules)

    def _has_active_descendant(mod: str) -> bool:
        prefix = mod + "."
        return any(counts.get(m, 0) > 0 for m in modules if m.startswith(prefix))

    for mod, path in sorted(modules.items()):
        if mod in ENTRY_MODULE_PATHS:
            continue
        if any(mod.endswith(s) for s in ENTRY_MODULE_SUFFIXES):
            continue
        if path.name == "__init__.py":
            continue
        if _has_active_descendant(mod):
            continue
        if any(part in ORPHAN_EXCLUDE_PATH_PARTS for part in path.parts):
            continue
        if is_allowed("orphan_modules", mod, allowlist):
            continue
        if counts.get(mod, 0) > 0:
            continue
        result.findings.append(
            Finding(
                category=Category.ORPHAN_MODULE,
                severity=Severity.WARNING,
                message=f"Module has no static inbound imports: {mod}",
                location=str(path.relative_to(ROOT)),
                symbol=mod,
                checker="orphan_modules",
                hint="Delete module or wire into pipeline; whitelist if entry/plugin hook",
            )
        )
    result.duration_ms = int((time.perf_counter() - t0) * 1000)
    return result


def check_orphan_configs(allowlist: dict | None = None) -> CheckResult:
    """YAML configs with no reference in Python/docs/CI."""
    allowlist = allowlist or load_allowlist()
    t0 = time.perf_counter()
    result = CheckResult(name="orphan_configs")
    if not CONFIGS_YAML.is_dir():
        result.skipped = True
        result.skip_reason = "configs/yaml missing"
        return result

    for path in sorted(CONFIGS_YAML.rglob("*.yaml")):
        rel = str(path.relative_to(ROOT))
        name = path.name
        stem = path.stem
        if is_allowed("orphan_configs", rel, allowlist):
            continue
        refs = string_references_in_repo(name) + string_references_in_repo(stem)
        if refs == 0:
            result.findings.append(
                Finding(
                    category=Category.ORPHAN_CONFIG,
                    severity=Severity.WARNING,
                    message=f"Config file has no textual references in repo: {name}",
                    location=rel,
                    checker="orphan_configs",
                    hint="Wire into loader or remove stale yaml",
                )
            )
    result.duration_ms = int((time.perf_counter() - t0) * 1000)
    return result


def check_orphan_scripts(allowlist: dict | None = None) -> CheckResult:
    """Scripts/tools never referenced outside their own file."""
    allowlist = allowlist or load_allowlist()
    t0 = time.perf_counter()
    result = CheckResult(name="orphan_scripts")

    candidates: list[Path] = []
    for base in (SCRIPTS, TOOLS):
        if base.is_dir():
            candidates.extend(p for p in base.rglob("*.py") if p.name != "__init__.py")

    for path in sorted(candidates):
        rel = str(path.relative_to(ROOT))
        if is_allowed("orphan_scripts", rel, allowlist):
            continue
        stem = path.stem
        # referenced by filename in repo (excluding self)
        refs = 0
        for root_file in py_files(ROOT):
            if root_file == path:
                continue
            try:
                text = root_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if stem in text or rel in text:
                refs += 1
        for doc in ROOT.rglob("*.md"):
            if any(part in EXCLUDE_DIR_NAMES for part in doc.parts):
                continue
            try:
                text = doc.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if stem in text or rel in text:
                refs += 1
        ci = ROOT / ".github" / "workflows" / "ci.yml"
        if ci.is_file() and (stem in ci.read_text(encoding="utf-8") or rel in ci.read_text(encoding="utf-8")):
            refs += 1
        if refs == 0:
            result.findings.append(
                Finding(
                    category=Category.ORPHAN_SCRIPT,
                    severity=Severity.INFO,
                    message=f"Script not referenced in docs, CI, or other code: {path.name}",
                    location=rel,
                    checker="orphan_scripts",
                    hint="Document in README, wire to CI, or remove",
                )
            )
    result.duration_ms = int((time.perf_counter() - t0) * 1000)
    return result


def check_commented_blocks(allowlist: dict | None = None, *, min_lines: int = 4) -> CheckResult:
    """Detect large blocks of commented-out code (AST-free heuristic)."""
    allowlist = allowlist or load_allowlist()
    t0 = time.perf_counter()
    result = CheckResult(name="commented_blocks")
    code_like = re.compile(r"^\s*#\s*(def |class |import |from |if |for |return |self\.|[a-zA-Z_][\w]*\s*=)")
    section_label = re.compile(r"^[A-Za-z][\w\s\-]*:\s")

    def _is_commented_code_line(line: str) -> bool:
        if not code_like.match(line):
            return False
        body = line.strip().lstrip("#").strip()
        if not body:
            return False
        # Skip CJK-heavy documentation comments (e.g. "# 计算置信度")
        ascii_chars = sum(1 for ch in body if ord(ch) < 128)
        if ascii_chars / max(len(body), 1) < 0.5:
            return False
        # Skip section labels (e.g. "# Level 1: Top-level headers")
        if section_label.match(body):
            return False
        return True

    for base in (ROOT / "docmirror", SCRIPTS, TOOLS):
        for path in py_files(base):
            rel = str(path.relative_to(ROOT))
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            run = 0
            run_start = 0
            for idx, line in enumerate(lines, start=1):
                if _is_commented_code_line(line):
                    if run == 0:
                        run_start = idx
                    run += 1
                else:
                    if run >= min_lines:
                        key = f"{rel}:{run_start}"
                        if not is_allowed("commented_blocks", key, allowlist):
                            result.findings.append(
                                Finding(
                                    category=Category.COMMENTED_CODE,
                                    severity=Severity.WARNING,
                                    message=f"{run} consecutive commented code-like lines",
                                    location=f"{rel}:{run_start}",
                                    checker="commented_blocks",
                                    hint="Delete dead code or restore with tests",
                                )
                            )
                    run = 0
    result.duration_ms = int((time.perf_counter() - t0) * 1000)
    return result
