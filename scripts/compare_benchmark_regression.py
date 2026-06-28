#!/usr/bin/env python3
"""Compare current benchmark results against a baseline and report regressions."""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

REGRESSION_METRICS = ["table_f1","text_f1","kv_f1","table_structure_score","char_preservation_rate","reading_order_score"]

def load_manifest(path: Path) -> dict:
    with open(path) as f: return json.load(f)

def compare_manifests(current: dict, baseline: dict, threshold: float) -> list[dict]:
    current_records = {r["golden_case_id"]: r for r in current.get("records", [])}
    baseline_records = {r["golden_case_id"]: r for r in baseline.get("records", [])}
    regressions = []
    for case_id, cur_record in current_records.items():
        base_record = baseline_records.get(case_id)
        if base_record is None: continue
        for metric in REGRESSION_METRICS:
            cur_val = cur_record.get(metric, 0.0)
            base_val = base_record.get(metric, 0.0)
            delta = cur_val - base_val
            if delta < -threshold:
                regressions.append({"golden_case_id": case_id, "document_type": cur_record.get("document_type",""), "metric": metric, "current_value": cur_val, "baseline_value": base_val, "delta": delta})
    regressions.sort(key=lambda r: r["delta"])
    return regressions

def generate_report(regressions: list[dict], current: dict, baseline: dict) -> str:
    lines = [f"# Benchmark Regression Report", f"", f"Generated: {datetime.now(timezone.utc).isoformat()}", f"", f"- **Current**: {current.get('release_tag','HEAD')}", f"- **Baseline**: {baseline.get('release_tag','baseline')}", f"- **Records compared**: {len(current.get('records',[]))}", f""]
    if not regressions:
        lines += ["## No Regressions Detected", "", "All metrics are within threshold.", ""]
        return "\n".join(lines)
    lines += [f"## Regressions Found ({len(regressions)})", "", "| Case ID | Document Type | Metric | Baseline | Current | Delta |", "|---------|--------------|--------|----------|---------|-------|"]
    for r in regressions:
        lines.append(f"| {r['golden_case_id']} | {r['document_type']} | {r['metric']} | {r['baseline_value']:.4f} | {r['current_value']:.4f} | {r['delta']:.4f} |")
    lines += ["", "### Summary", "", f"- **Affected cases**: {len(set(r['golden_case_id'] for r in regressions))}", f"- **Worst regression**: {regressions[0]['golden_case_id']} {regressions[0]['metric']} ({regressions[0]['delta']:.4f})", "", "### Action Required", "", "1. Verify the regression is expected", "2. Update the baseline if intentional", "3. Add a comment explaining the regression", ""]
    return "\n".join(lines)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--threshold", type=float, default=0.01)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if not args.current.exists():
        print(f"Current manifest not found: {args.current}", file=sys.stderr); return 1
    if not args.baseline.exists():
        report = generate_report([], {"release_tag":"HEAD","records":[]}, {"release_tag":"N/A","records":[]})
        if args.output: args.output.write_text(report)
        print("No baseline found — skipping"); return 0
    current = load_manifest(args.current)
    baseline = load_manifest(args.baseline)
    regressions = compare_manifests(current, baseline, args.threshold)
    report = generate_report(regressions, current, baseline)
    if args.output: args.output.write_text(report)
    if regressions:
        print(f"Found {len(regressions)} regressions exceeding {args.threshold} threshold")
        return 1
    else:
        print("No regressions detected")
        return 0

if __name__ == "__main__": sys.exit(main())
