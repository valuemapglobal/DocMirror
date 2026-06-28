#!/usr/bin/env python3
"""Run competitor baselines on the same golden matrix for comparison.

Usage:
    python scripts/benchmark_competitors.py \\
        --matrix docs/benchmarks/golden-matrix.json \\
        --output docs/benchmarks/competitors/

This script runs PyMuPDF and other baselines on the golden matrix
and produces JSON output compatible with the BenchmarkManifest format.

Design (GA1.0-EC-01 §Component 4.4):
    Competitor results are stored in ``docs/benchmarks/competitors/``
    and merged by the comparison table generator into COMPARISON.md.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def run_pymupdf_baseline(
    file_path: str,
) -> dict[str, float]:
    """Run PyMuPDF text extraction as a baseline.

    Args:
        file_path: Path to the document file.

    Returns:
        Dict of metrics: char_count, table_count, elapsed_ms.
    """
    import fitz  # PyMuPDF

    start = time.perf_counter()
    doc = fitz.open(file_path)

    char_count = 0
    table_count = 0

    for page in doc:
        text = page.get_text("text")
        char_count += len(text)

        # PyMuPDF has basic table detection via find_tables()
        try:
            tables = page.find_tables()
            table_count += len(tables.tables)
        except Exception:
            pass

    elapsed_ms = (time.perf_counter() - start) * 1000
    doc.close()

    return {
        "char_count": char_count,
        "table_count": table_count,
        "elapsed_ms": round(elapsed_ms, 2),
    }


def run_unstructured_baseline(
    file_path: str,
) -> dict[str, float]:
    """Run Unstructured.io as a baseline.

    Requires: pip install "unstructured[pdf]"

    Args:
        file_path: Path to the document file.

    Returns:
        Dict of metrics: char_count, table_count, element_count, elapsed_ms.
    """
    try:
        from unstructured.partition.auto import partition
    except ImportError:
        return {
            "error": "unstructured not installed. Install with: pip install 'unstructured[pdf]'",
            "char_count": 0,
            "table_count": 0,
            "element_count": 0,
            "elapsed_ms": 0.0,
        }

    start = time.perf_counter()
    elements = partition(filename=file_path)
    elapsed_ms = (time.perf_counter() - start) * 1000

    char_count = sum(len(str(e)) for e in elements)
    table_count = sum(1 for e in elements if e.category == "Table")
    element_count = len(elements)

    return {
        "char_count": char_count,
        "table_count": table_count,
        "element_count": element_count,
        "elapsed_ms": round(elapsed_ms, 2),
    }


def run_baselines(
    golden_matrix_path: str,
    output_dir: str,
) -> dict[str, Any]:
    """Run all competitor baselines on the golden matrix.

    Args:
        golden_matrix_path: Path to golden-matrix.json.
        output_dir: Directory to write baseline results.

    Returns:
        Dict mapping competitor names to their result files.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    import importlib.util

    from docmirror.eval.golden_loader import load_golden_matrix
    from docmirror.eval.golden_loader import load_golden_matrix_from_file

    matrix_path = Path(golden_matrix_path)
    if matrix_path.is_file() and matrix_path.suffix == ".json":
        cases = load_golden_matrix_from_file(matrix_path)
    else:
        cases = load_golden_matrix(matrix_path)
    print(f"Running baselines on {len(cases)} golden cases...")

    results: dict[str, list[dict[str, Any]]] = {
        "pymupdf": [],
        "unstructured": [],
    }

    for case in cases:
        if not case.file_path or not case.file_path.exists():
            continue

        file_path = str(case.file_path)
        case_id = case.case_id or case.name or "unknown"

        # PyMuPDF baseline
        if importlib.util.find_spec("fitz"):
            try:
                metrics = run_pymupdf_baseline(file_path)
                results["pymupdf"].append({
                    "golden_case_id": case_id,
                    "document_type": case.document_type or "unknown",
                    "metrics": metrics,
                })
                print(f"  ✓ pymupdf  {case_id}")
            except Exception as e:
                print(f"  ✗ pymupdf  {case_id}: {e}")
        else:
            print("  ! pymupdf not installed, skipping")

        # Unstructured baseline
        if importlib.util.find_spec("unstructured"):
            try:
                metrics = run_unstructured_baseline(file_path)
                results["unstructured"].append({
                    "golden_case_id": case_id,
                    "document_type": case.document_type or "unknown",
                    "metrics": metrics,
                })
                print(f"  ✓ unstructured  {case_id}")
            except Exception as e:
                print(f"  ✗ unstructured  {case_id}: {e}")
        else:
            print("  ! unstructured not installed, skipping")

    # Write per-competitor results
    manifest: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "competitors": {},
    }
    for competitor, records in results.items():
        file_name = f"{competitor}.json"
        file_path = output_path / file_name
        file_path.write_text(json.dumps(records, indent=2, ensure_ascii=False))
        manifest["competitors"][competitor] = file_name
        print(f"Wrote {len(records)} records to {file_path}")

    # Write manifest
    manifest_path = output_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"Manifest written to {manifest_path}")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run competitor baselines on golden matrix")
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

    run_baselines(args.matrix, args.output)
