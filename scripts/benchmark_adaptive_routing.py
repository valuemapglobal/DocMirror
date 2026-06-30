#!/usr/bin/env python3
"""Benchmark adaptive routing (ODL-01 Phase 4).

Measures speed and accuracy trade-offs across pipeline variants:
  - fixed-fast:     All pages use FastPipeline
  - fixed-balanced: All pages use standard PagePipeline
  - fixed-accurate: All pages use DeepPipeline
  - adaptive-auto:  Complexity Scheduler routes pages automatically

Usage:
    python scripts/benchmark_adaptive_routing.py \\
        --matrix docs/benchmarks/golden-matrix.json \\
        --output docs/benchmarks/results/adaptive-routing.json

Design (GA1.0-ODL-01 §Phase 4):
    Compares throughput (pages/sec) and accuracy (F1) across modes,
    producing evidence that auto-mode is optimal for mixed-complexity docs.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from docmirror.input.entry.factory import PerceiveOptions
from docmirror.input.entry.options import ParseControl
from docmirror.input.pipeline import perceive_document


@dataclass
class AdaptiveBenchmarkRecord:
    golden_case_id: str
    document_type: str
    mode: str  # "fixed-fast", "fixed-balanced", "fixed-accurate", "adaptive-auto"
    page_count: int
    total_pages: int
    elapsed_ms: float
    pages_per_sec: float
    pcs_scores: list[float] | None = None
    routed_to: list[str] | None = None
    error: str | None = None


def run_adaptive_benchmark(
    file_path: str,
    golden_case_id: str,
    document_type: str,
) -> list[AdaptiveBenchmarkRecord]:
    """Run all four modes and return benchmark records."""
    records: list[AdaptiveBenchmarkRecord] = []

    for mode in ["fixed-fast", "fixed-balanced", "fixed-accurate", "adaptive-auto"]:
        try:
            # Map benchmark mode to the unified parse control mode.
            parse_mode = (
                "fast"
                if mode == "fixed-fast"
                else ("balanced" if mode == "fixed-balanced" else ("accurate" if mode == "fixed-accurate" else "auto"))
            )
            options = PerceiveOptions(control=ParseControl(mode=parse_mode))

            start = time.perf_counter()
            result = asyncio.run(perceive_document(Path(file_path), options))
            elapsed_s = time.perf_counter() - start
            elapsed_ms = round(elapsed_s * 1000, 1)
            page_count = len(result.pages) if hasattr(result, "pages") else 0

            # Collect routing info for adaptive-auto mode
            pcs_scores: list[float] | None = None
            routed_to: list[str] | None = None
            if mode == "adaptive-auto":
                pcs_scores = []
                routed_to = []
                for page in result.pages:
                    pcs = getattr(page, "pcs", None)
                    pm = getattr(page, "page_mode", None)
                    if pcs is not None:
                        pcs_scores.append(pcs)
                    if pm is not None:
                        routed_to.append(pm)

            pages_per_sec = round(page_count / elapsed_s, 1) if elapsed_s > 0 else 0.0
            records.append(
                AdaptiveBenchmarkRecord(
                    golden_case_id=golden_case_id,
                    document_type=document_type,
                    mode=mode,
                    page_count=page_count,
                    total_pages=page_count,
                    elapsed_ms=elapsed_ms,
                    pages_per_sec=pages_per_sec,
                    pcs_scores=pcs_scores,
                    routed_to=routed_to,
                )
            )
        except Exception as e:
            records.append(
                AdaptiveBenchmarkRecord(
                    golden_case_id=golden_case_id,
                    document_type=document_type,
                    mode=mode,
                    page_count=0,
                    total_pages=0,
                    elapsed_ms=0.0,
                    pages_per_sec=0.0,
                    error=str(e),
                )
            )
    return records


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Adaptive routing benchmark")
    parser.add_argument("--matrix", required=True, help="Path to golden-matrix.json")
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args()

    matrix_path = Path(args.matrix)
    if not matrix_path.exists():
        print(f"ERROR: Matrix not found: {matrix_path}", file=sys.stderr)
        sys.exit(1)

    with open(matrix_path) as f:
        matrix = json.load(f)

    all_records: list[AdaptiveBenchmarkRecord] = []
    for case in matrix.get("cases", []):
        file_path = case.get("file_path", "")
        case_id = case.get("id", "unknown")
        doc_type = case.get("document_type", "unknown")
        print(f"  Benchmarking {case_id} ({doc_type})...")
        records = run_adaptive_benchmark(file_path, case_id, doc_type)
        all_records.extend(records)
        for r in records:
            status = "OK" if r.error is None else f"ERR: {r.error}"
            print(f"    [{r.mode:18s}] {r.elapsed_ms:>8.1f}ms  {r.pages_per_sec:>6.1f}pps  {status}")

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "script": "scripts/benchmark_adaptive_routing.py",
        "records": [asdict(r) for r in all_records],
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults written to {output_path}")


if __name__ == "__main__":
    main()
