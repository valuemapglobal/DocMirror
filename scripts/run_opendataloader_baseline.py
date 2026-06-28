#!/usr/bin/env python3
"""Run OpenDataLoader on the golden matrix for comparison.

Usage:
    python scripts/run_opendataloader_baseline.py \
        --matrix docs/benchmarks/golden-matrix.json \
        --output docs/benchmarks/competitors/

Requires:
    pip install opendataloader-pdf

Design (GA1.0-ODL-03 §Implementation 1):
    Runs OpenDataLoader's CLI on each golden case PDF and collects
    metrics: char_count, table_count, element_count, elapsed_ms.
    Output is compatible with generate_benchmark_table.py's competitor format.

Note:
    OpenDataLoader uses a Java backend. First run may be slow
    as it downloads the JVM dependency (~100MB).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _is_opendataloader_installed() -> bool:
    """Check if OpenDataLoader CLI is available."""
    return shutil.which("opd") is not None


def run_opendataloader_on_file(file_path: str) -> dict[str, float]:
    """Run OpenDataLoader on a single file and return metrics.

    Args:
        file_path: Path to the document file.

    Returns:
        Dict of metrics: char_count, table_count, element_count, elapsed_ms.
    """
    if not _is_opendataloader_installed():
        # Try Python API fallback
        try:
            return _run_via_python_api(file_path)
        except ImportError:
            return {
                "error": "OpenDataLoader not installed. Install with: pip install opendataloader-pdf",
                "char_count": 0,
                "table_count": 0,
                "element_count": 0,
                "elapsed_ms": 0.0,
            }

    start = time.perf_counter()

    # Use tmpdir for output to avoid cluttering working directory
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            ["opd", "parse", file_path, "--output-dir", tmpdir, "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            return {
                "error": f"OpenDataLoader failed: {result.stderr[:200]}",
                "char_count": 0,
                "table_count": 0,
                "element_count": 0,
                "elapsed_ms": 0.0,
            }

        # Parse output JSON
        output_files = list(Path(tmpdir).glob("*.json"))
        if not output_files:
            return {
                "error": "No OpenDataLoader output files found",
                "char_count": 0,
                "table_count": 0,
                "element_count": 0,
                "elapsed_ms": 0.0,
            }

        # Aggregate from output
        char_count = 0
        table_count = 0
        element_count = 0

        for of in output_files:
            data = json.loads(of.read_text())
            pages = data.get("pages", [data]) if isinstance(data, dict) else data
            for page in (pages if isinstance(pages, list) else [pages]):
                elements = page.get("elements", page.get("content", []))
                if isinstance(elements, list):
                    element_count += len(elements)
                    for el in elements:
                        text = el.get("text", "") if isinstance(el, dict) else str(el)
                        char_count += len(text)
                        if isinstance(el, dict) and el.get("type") == "table":
                            table_count += 1
                elif isinstance(elements, str):
                    char_count += len(elements)

    elapsed_ms = (time.perf_counter() - start) * 1000

    return {
        "char_count": char_count,
        "table_count": table_count,
        "element_count": element_count,
        "elapsed_ms": round(elapsed_ms, 2),
    }


def _run_via_python_api(file_path: str) -> dict[str, float]:
    """Fallback: run OpenDataLoader via its Python API.

    Requires: pip install opendataloader-pdf
    """
    try:
        from opendataloader import DocumentLoader
    except ImportError:
        raise ImportError("OpenDataLoader not available via CLI or Python API")

    start = time.perf_counter()

    doc = DocumentLoader.load(file_path)
    elapsed_ms = (time.perf_counter() - start) * 1000

    char_count = 0
    table_count = 0
    element_count = 0

    if hasattr(doc, "pages"):
        for page in doc.pages:
            if hasattr(page, "elements"):
                for el in page.elements:
                    element_count += 1
                    text = getattr(el, "text", "") or ""
                    char_count += len(text)
                    if getattr(el, "type", "") == "table":
                        table_count += 1

    return {
        "char_count": char_count,
        "table_count": table_count,
        "element_count": element_count,
        "elapsed_ms": round(elapsed_ms, 2),
    }


def run_baseline(
    golden_matrix_path: str,
    output_dir: str,
) -> dict[str, Any]:
    """Run OpenDataLoader on all golden cases.

    Args:
        golden_matrix_path: Path to golden-matrix.json.
        output_dir: Directory to write baseline results.

    Returns:
        Dict with results metadata.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    try:
        from docmirror.eval.golden_loader import load_golden_matrix
        from docmirror.eval.golden_loader import load_golden_matrix_from_file
    except ImportError:
        print("Error: must run from DocMirror repo root with docmirror installed")
        sys.exit(1)

    matrix_path = Path(golden_matrix_path)
    if matrix_path.is_file() and matrix_path.suffix == ".json":
        cases = load_golden_matrix_from_file(matrix_path)
    else:
        cases = load_golden_matrix(matrix_path)
    print(f"Running OpenDataLoader on {len(cases)} golden cases...")

    records: list[dict[str, Any]] = []

    for case in cases:
        if not case.file_path or not case.file_path.exists():
            continue

        file_path = str(case.file_path)
        case_id = case.case_id or case.name or "unknown"

        try:
            metrics = run_opendataloader_on_file(file_path)
            records.append({
                "golden_case_id": case_id,
                "document_type": case.document_type or "unknown",
                "format": getattr(case, "format", "pdf"),
                "metrics": metrics,
            })
            if "error" in metrics:
                print(f"  ! opendataloader  {case_id}: {metrics['error'][:60]}")
            else:
                print(f"  ✓ opendataloader  {case_id}  ({metrics['elapsed_ms']:.0f}ms)")
        except Exception as e:
            print(f"  ✗ opendataloader  {case_id}: {e}")
            records.append({
                "golden_case_id": case_id,
                "document_type": case.document_type or "unknown",
                "format": getattr(case, "format", "pdf"),
                "metrics": {
                    "error": str(e)[:200],
                    "char_count": 0,
                    "table_count": 0,
                    "element_count": 0,
                    "elapsed_ms": 0.0,
                },
            })

    # Write results
    file_name = "opendataloader.json"
    file_path = output_path / file_name
    file_path.write_text(json.dumps(records, indent=2, ensure_ascii=False))
    print(f"\nWrote {len(records)} records to {file_path}")

    # Update manifest
    manifest_path = output_path / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    else:
        manifest = {"generated_at": datetime.now(timezone.utc).isoformat(), "competitors": {}}
    manifest["competitors"]["opendataloader"] = file_name
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"Manifest updated at {manifest_path}")

    return {"records_count": len(records), "competitor": "opendataloader"}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run OpenDataLoader baseline on golden matrix"
    )
    parser.add_argument(
        "--matrix",
        default="docs/benchmarks/golden-matrix.json",
        help="Path to golden-matrix.json",
    )
    parser.add_argument(
        "--output",
        default="docs/benchmarks/competitors/",
        help="Output directory for baseline results",
    )
    args = parser.parse_args()

    run_baseline(args.matrix, args.output)
