# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Golden test case loader for the evaluation matrix.

Discovers fixture files and expected-oracle metadata under a golden root
directory, yielding ``GoldenCase`` records consumed by ``benchmark_runner`` and
TQG manifest expansion. Supports tier tags, document-type labels, and
per-case gate overrides embedded in sidecar JSON.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GoldenCase:
    """Single golden test case."""

    id: str
    file_path: Path
    document_type: str = "generic"
    expected: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


def load_golden_matrix(root: Path | None = None) -> list[GoldenCase]:
    """Load golden cases from tests/golden/ directory tree.

    Expected layout::

        tests/golden/
          manifest.json          # optional index
          generic/
            case_001/
              input.pdf
              expected.json
          credit_report/
            ...
    """
    root = root or Path("tests/golden")
    if not root.exists():
        return []

    cases: list[GoldenCase] = []

    manifest = root / "manifest.json"
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        # Flat list format
        for entry in data.get("cases", []):
            case = _case_from_entry(root, entry)
            if case:
                cases.append(case)
        # Suite format (EFPA manifest)
        for suite in (data.get("suites") or {}).values():
            for entry in suite.get("cases", []):
                if entry.get("optional") and not (root / entry["path"]).exists():
                    continue
                case = _case_from_entry(root, entry)
                if case:
                    cases.append(case)
        if cases:
            cases.extend(_discover_real_credit_cases(root))
            return _dedupe_golden_cases(cases)

    # Auto-discover: any directory with input file + expected.json
    for expected_file in root.rglob("expected.json"):
        case_dir = expected_file.parent
        input_files = list(case_dir.glob("input.*")) + list(case_dir.glob("*.pdf"))
        if not input_files:
            continue
        doc_type = case_dir.parent.name if case_dir.parent != root else "generic"
        cases.append(
            GoldenCase(
                id=case_dir.name,
                file_path=input_files[0],
                document_type=doc_type,
                expected=json.loads(expected_file.read_text(encoding="utf-8")),
            )
        )
    cases.extend(_discover_real_credit_cases(root))
    return _dedupe_golden_cases(cases)


def _dedupe_golden_cases(cases: list[GoldenCase]) -> list[GoldenCase]:
    seen: set[str] = set()
    out: list[GoldenCase] = []
    for case in cases:
        key = str(case.file_path.resolve())
        if key in seen or not case.file_path.suffix.lower() == ".pdf":
            continue
        seen.add(key)
        out.append(case)
    return out


def _discover_real_credit_cases(golden_root: Path) -> list[GoldenCase]:
    """Optional real credit PDFs: tests/fixtures/credit_reports/{id}.pdf + raw JSON."""
    repo_root = golden_root.parent.parent if golden_root.name == "golden" else golden_root.parent
    fixture_dir = repo_root / "tests" / "fixtures" / "credit_reports"
    baseline_dir = golden_root / "credit_report" / "baseline_outputs"
    if not fixture_dir.is_dir() or not baseline_dir.is_dir():
        return []
    cases: list[GoldenCase] = []
    for pdf in sorted(fixture_dir.glob("*.pdf")):
        raw = baseline_dir / f"{pdf.stem}.json"
        if not raw.exists():
            continue
        expected = json.loads(raw.read_text(encoding="utf-8"))
        cases.append(
            GoldenCase(
                id=f"real_{pdf.stem}",
                file_path=pdf,
                document_type="credit_report",
                expected=expected,
                tags=["credit_report", "real"],
            )
        )
    return cases


def _case_from_entry(root: Path, entry: dict) -> GoldenCase | None:
    fp = root / entry["path"]
    if fp.suffix.lower() != ".pdf":
        return None
    expected_path = fp.parent / "expected.json"
    expected: dict[str, Any] = {}
    if expected_path.exists():
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
    elif entry.get("thresholds"):
        expected = {"thresholds": entry["thresholds"]}
    return GoldenCase(
        id=entry.get("id", fp.stem),
        file_path=fp,
        document_type=entry.get("document_type", "generic"),
        expected=expected,
        tags=entry.get("tags", []),
    )


def load_golden_matrix_from_file(
    matrix_path: str | Path,
    *,
    base_dir: str | Path | None = None,
) -> list[GoldenCase]:
    """Load golden cases from a JSON matrix file.

    The matrix file follows this shape:

    .. code-block:: json

        {"matrix_version": "1.0", "cases": [{"id": "...", "document_type": "...", "source_path": "..."}]}

    Args:
        matrix_path: Path to a JSON golden matrix file.
        base_dir: Optional base directory for resolving relative
            ``source_path`` values. Defaults to the matrix file's parent.

    Returns:
        List of GoldenCase objects.
    """
    matrix_path = Path(matrix_path)
    if not matrix_path.exists():
        raise FileNotFoundError(f"Golden matrix file not found: {matrix_path}")

    base = Path(base_dir) if base_dir else matrix_path.resolve().parent

    with open(matrix_path) as f:
        data = json.load(f)

    cases: list[GoldenCase] = []
    for entry in data.get("cases", []):
        case_id = entry.get("id", "unknown")
        doc_type = entry.get("document_type", "generic")
        source_path = entry.get("source_path") or entry.get("source_fixture", "")

        file_path = None
        if source_path:
            candidate = base / source_path
            if candidate.exists():
                file_path = candidate
            else:
                from_project = Path(source_path)
                if from_project.exists():
                    file_path = from_project

        case = GoldenCase(
            id=case_id,
            file_path=file_path,
            document_type=doc_type,
            expected={},
            tags=entry.get("tags", []),
        )
        cases.append(case)

    return cases
