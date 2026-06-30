#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Design 19 G2/G3 — fail CI when production code reads removed mirror JSON paths."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCMIRROR = REPO_ROOT / "docmirror"

# G2: document.micro_grids reads (emit/write allowed in parse_result only)
G2_ALLOWED_SUFFIXES = {
    "models/mirror/page_access.py",
    "models/entities/parse_result.py",
}

G2_PATTERNS = (
    re.compile(r"""document\.get\(\s*["']micro_grids["']"""),
    re.compile(r"""document\[\s*["']micro_grids["']\s*\]"""),
)

# G3: forensic evidence structures used as SSOT (fallback readers allowed)
G3_ALLOWED_SUFFIXES = {
    "models/mirror/page_access.py",
    "models/mirror/domain_access.py",
    "models/entities/parse_result.py",
    "input/bridge/parse_result_bridge.py",
    "ocr/scanned/analyze_page.py",
    "input/extraction/extractor.py",
    "eval/tqg/runner.py",
    "plugins/_base/kv_community_enrich.py",
}

G3_PATTERNS = (
    re.compile(r"""\.get\(\s*["']structures["']\s*\)"""),
    re.compile(r"""scanned_local_structure_evidence"""),
)


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _scan_py(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _line_allowed_for_g2(rel: str) -> bool:
    return any(rel.endswith(suffix) for suffix in G2_ALLOWED_SUFFIXES)


def _line_allowed_for_g3(rel: str) -> bool:
    return any(rel.endswith(suffix) for suffix in G3_ALLOWED_SUFFIXES)


def check_g2() -> list[str]:
    errors: list[str] = []
    for path in _scan_py(DOCMIRROR):
        rel = _rel(path)
        if _line_allowed_for_g2(rel):
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if any(p.search(line) for p in G2_PATTERNS):
                errors.append(f"G2 {rel}:{lineno}: direct document.micro_grids access")
    return errors


def check_g3() -> list[str]:
    errors: list[str] = []
    for path in _scan_py(DOCMIRROR):
        rel = _rel(path)
        if _line_allowed_for_g3(rel):
            continue
        text = path.read_text(encoding="utf-8")
        if "scanned_local_structure_evidence" not in text:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "scanned_local_structure_evidence" in line and ("structures" in line or '.get("structures")' in line):
                errors.append(f"G3 {rel}:{lineno}: scanned_local_structure_evidence structures SSOT")
    return errors


def main() -> int:
    errors = check_g2() + check_g3()
    if errors:
        print("PageProjection removed reference gate FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        print(
            "Allowed readers: page_access and domain_access (G3); "
            "see internal page-centric mirror unification plan",
            file=sys.stderr,
        )
        return 1
    print("PageProjection removed reference gate OK (G2 micro_grids + G3 local_structure evidence)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
