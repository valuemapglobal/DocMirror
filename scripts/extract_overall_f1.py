#!/usr/bin/env python3
"""Extract overall F1 from a benchmark manifest for README badge generation.

Usage:
    python scripts/extract_overall_f1.py docs/benchmarks/results/latest.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def extract_overall_f1(manifest_path: str) -> float:
    """Extract the overall F1 score from a BenchmarkManifest JSON file.

    Args:
        manifest_path: Path to the manifest JSON.

    Returns:
        The average F1 across table, text, and KV categories,
        or 0.0 if not available.
    """
    data = json.loads(Path(manifest_path).read_text())
    summary = data.get("summary", {})
    f1_scores = [
        summary.get("avg_table_f1", 0),
        summary.get("avg_text_f1", 0),
        summary.get("avg_kv_f1", 0),
    ]
    return round(sum(f1_scores) / len(f1_scores), 4)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "docs/benchmarks/results/latest.json"
    f1 = extract_overall_f1(path)
    print(f1)
