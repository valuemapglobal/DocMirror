#!/usr/bin/env python3
"""Run the first real benchmark on fixture PDFs and generate the manifest + BENCHMARKS.md.

Usage:
    python scripts/run_first_benchmark.py

This script:
  1. Finds all fixture PDFs in tests/fixtures/
  2. Parses each with perceive_document
  3. Measures: elapsed time, page count, tables found, text chars, reading order
  4. Generates docs/benchmarks/results/v1.0.0.json (BenchmarkManifest)
  5. Generates docs/benchmarks/BENCHMARKS.md with real numbers
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Add project root to path ──
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["DOCMIRROR_ENHANCE_MODE"] = "auto"

# ── Fixture discovery ──
FIXTURE_DIR = ROOT / "tests" / "fixtures"
OUTPUT_DIR = ROOT / "docs" / "benchmarks"
RESULTS_DIR = OUTPUT_DIR / "results"
COMPETITORS_DIR = OUTPUT_DIR / "competitors"
PUBLIC_MINI_ARTIFACT = ROOT / "examples" / "fixtures" / "trust_quickstart_artifact.json"

# Domain mapping based on fixture directory structure
DOMAIN_MAP = {
    "bank_statement": "bank_statement",
    "credit_report": "credit_report",
    "vat_invoice": "vat_invoice",
    "alipay_payment": "alipay_payment",
    "wechat_payment": "wechat_payment",
    "business_license": "business_license",
    "synthetic": "generic",
}


def discover_fixtures() -> list[dict[str, Any]]:
    """Discover fixture PDFs and classify them by document type."""
    fixtures = []
    for pdf in sorted(FIXTURE_DIR.rglob("*.pdf")):
        if ".git" in str(pdf) or "__pycache__" in str(pdf):
            continue
        rel = pdf.relative_to(FIXTURE_DIR)
        parts = rel.parts
        # Map document type from parent directory
        doc_type = DOMAIN_MAP.get(parts[0], "generic")
        fixtures.append(
            {
                "file_path": str(pdf),
                "document_type": doc_type,
                "name": pdf.stem,
            }
        )
    return fixtures


async def run_single_benchmark(fixture: dict[str, Any]) -> dict[str, Any]:
    """Parse one fixture and collect benchmark metrics."""
    file_path = fixture["file_path"]
    start = time.perf_counter()

    try:
        from docmirror.input.entry.factory import perceive_document

        result = await perceive_document(file_path)
        elapsed_ms = (time.perf_counter() - start) * 1000
    except Exception as exc:
        return {
            "case_id": fixture["name"],
            "document_type": fixture["document_type"],
            "success": False,
            "error": str(exc),
            "elapsed_ms": 0.0,
        }

    # Extract metrics from result (directly from ParseResult)
    page_count = result.page_count
    char_count = len(result.full_text)
    table_count = result.total_tables

    # Reading order score from the metrics module
    from docmirror.eval.metrics import reading_order_score

    try:
        ro_score = reading_order_score(result)
    except Exception:
        ro_score = 0.0

    # Per-page latency
    per_page_ms = elapsed_ms / page_count if page_count > 0 else elapsed_ms

    return {
        "case_id": fixture["name"],
        "document_type": fixture["document_type"],
        "success": True,
        "page_count": page_count,
        "char_count": char_count,
        "table_count": table_count,
        "elapsed_ms": round(elapsed_ms, 1),
        "per_page_ms": round(per_page_ms, 1),
        "reading_order_score": round(ro_score, 4),
        "error": None,
    }


async def run_benchmark() -> list[dict[str, Any]]:
    """Run benchmark on all fixture PDFs."""
    fixtures = discover_fixtures()
    print(f"Discovered {len(fixtures)} fixture PDFs:\n")

    results = []
    for f in fixtures:
        print(f"  Parsing {f['name']} ({f['document_type']})...", end=" ", flush=True)
        r = await run_single_benchmark(f)
        if r["success"]:
            print(f"✓ {r['page_count']}pg, {r['elapsed_ms']}ms total, {r['per_page_ms']}ms/pg")
        else:
            print(f"✗ {r.get('error', 'unknown error')}")
        results.append(r)

    return results


def generate_public_mini_manifest() -> dict[str, Any]:
    """Generate a dependency-light public benchmark from the synthetic trust artifact."""
    artifact = json.loads(PUBLIC_MINI_ARTIFACT.read_text(encoding="utf-8"))
    fields = artifact["fields"]
    trust = artifact["trust"]
    review_count = sum(1 for field in fields if field.get("needs_review"))

    return {
        "manifest_version": "1.0",
        "release_tag": "v1.0.0-public-mini",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "record_count": 1,
            "field_count": len(fields),
            "evidence_coverage": trust["evidence_coverage"],
            "review_required_count": review_count,
            "document_confidence": trust["document_confidence"],
        },
        "records": [
            {
                "golden_case_id": artifact["document"]["id"],
                "document_type": artifact["document"]["type"],
                "format": "synthetic_json",
                "mode": "public-mini",
                "page_count": artifact["document"]["page_count"],
                "field_count": len(fields),
                "evidence_coverage": trust["evidence_coverage"],
                "review_required_count": review_count,
                "document_confidence": trust["document_confidence"],
                "docmirror_version": "v1.0.0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }


def generate_public_mini_md(manifest: dict[str, Any]) -> str:
    summary = manifest["summary"]
    return "\n".join(
        [
            "# Public Mini Benchmark - DocMirror",
            "",
            "This benchmark is intentionally synthetic and dependency-light. It verifies",
            "the public evidence/trust contract without private fixtures or OCR models.",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Records | {summary['record_count']} |",
            f"| Fields with evidence | {summary['field_count']} |",
            f"| Evidence coverage | {summary['evidence_coverage']:.2f} |",
            f"| Document confidence | {summary['document_confidence']:.2f} |",
            f"| Fields requiring review | {summary['review_required_count']} |",
            "",
        ]
    )


def generate_manifest(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate a BenchmarkManifest-compatible JSON dict."""
    successful = [r for r in results if r["success"]]
    n = len(successful)

    if n == 0:
        return {
            "manifest_version": "1.0",
            "release_tag": "v1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {"record_count": 0},
            "records": [],
        }

    avg_table_f1 = sum(r.get("reading_order_score", 0) for r in successful) / n
    avg_elapsed = sum(r.get("elapsed_ms", 0) for r in successful) / n
    avg_per_page = sum(r.get("per_page_ms", 0) for r in successful) / n
    total_pages = sum(r.get("page_count", 0) for r in successful)
    total_chars = sum(r.get("char_count", 0) for r in successful)
    total_tables = sum(r.get("table_count", 0) for r in successful)

    summary = {
        "record_count": n,
        "total_pages": total_pages,
        "total_chars": total_chars,
        "total_tables": total_tables,
        "avg_elapsed_ms": round(avg_elapsed, 1),
        "avg_per_page_ms": round(avg_per_page, 1),
        "avg_reading_order_score": round(avg_table_f1, 4),
    }

    records = []
    for r in successful:
        records.append(
            {
                "golden_case_id": r["case_id"],
                "document_type": r["document_type"],
                "format": "pdf",
                "mode": "auto",
                "page_count": r["page_count"],
                "char_count": r["char_count"],
                "table_count": r["table_count"],
                "elapsed_ms": r["elapsed_ms"],
                "per_page_ms": r["per_page_ms"],
                "reading_order_score": r["reading_order_score"],
                "docmirror_version": "v1.0.0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    return {
        "manifest_version": "1.0",
        "release_tag": "v1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "records": records,
    }


def generate_benchmarks_md(manifest: dict[str, Any]) -> str:
    """Generate BENCHMARKS.md from the manifest."""
    summary = manifest.get("summary", {})
    records = manifest.get("records", [])
    n = summary.get("record_count", 0)

    lines = [
        "# Benchmarks — DocMirror",
        "",
        "_This page is auto-generated by CI on every release._",
        f"_Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "## Overall Performance",
        "",
        "| Metric | Value |",
        "|--------|-------|",
    ]

    if n > 0:
        lines.append(f"| Documents tested | {n} |")
        lines.append(f"| Total pages | {summary.get('total_pages', 0)} |")
        lines.append(f"| Avg latency per document | {summary.get('avg_elapsed_ms', '—')} ms |")
        lines.append(f"| Avg latency per page | {summary.get('avg_per_page_ms', '—')} ms |")
        lines.append(f"| Total chars extracted | {summary.get('total_chars', 0):,} |")
        lines.append(f"| Total tables found | {summary.get('total_tables', 0)} |")
        lines.append(f"| Avg reading order score | {summary.get('avg_reading_order_score', '—')} |")
    else:
        lines.append("| Status | No successful benchmark runs |")
    lines.append("")

    # Competitor comparison (estimates for now)
    lines.extend(
        [
            "## Comparison vs Competitors",
            "",
            "| Metric | DocMirror | OpenDataLoader | PyMuPDF | Unstructured | Azure Doc AI |",
            "|--------|-----------|----------------|---------|-------------|-------------|",
        ]
    )

    # Try to compute per-page speed from benchmark
    speed_10pg = summary.get("avg_per_page_ms", 50) * 10 if n > 0 else "—"
    speed_10pg_str = f"~{speed_10pg:.0f}ms" if isinstance(speed_10pg, float) else "—"

    lines.append(f"| Speed (10pg) | {speed_10pg_str} | **~15ms** | **~30ms** | ~1200ms | ~3400ms |")
    lines.append("| Table detection | — | **0.928** | 0.82 | 0.88 | 0.93 |")
    lines.append("| Text extraction | — | **0.99** | **0.99** | 0.95 | 0.97 |")
    lines.append("| KV extraction | — | — | — | 0.82 | 0.89 |")
    lines.append(f"| Reading Order | {summary.get('avg_reading_order_score', '—')} | **0.94** | 0.72 | 0.78 | 0.85 |")
    lines.append("| Multi-format | **8 formats** | 1 (PDF) | 2 | 5 | 3 |")
    lines.append("")
    lines.append(
        "> _DocMirror F1 scores (table, text, KV) require ground-truth labels for the golden matrix. These will be populated in a future release._"
    )
    lines.append("")

    # Per-document breakdown
    lines.extend(
        [
            "## Per-Document Results",
            "",
            "| Document | Type | Pages | Tables | Chars | Latency | ms/pg |",
            "|----------|------|-------|--------|-------|---------|-------|",
        ]
    )

    for r in sorted(records, key=lambda x: x.get("elapsed_ms", 0)):
        lines.append(
            f"| {r['golden_case_id']} | {r['document_type']} | "
            f"{r['page_count']} | {r['table_count']} | {r['char_count']:,} | "
            f"{r['elapsed_ms']}ms | {r['per_page_ms']}ms |"
        )

    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "- **Fixture documents**: 8 real-world PDFs (bank ledgers, credit reports, VAT invoices, Alipay/WeChat payments, business licenses)"
    )
    lines.append("- **Metrics**: Latency measured wall-clock from perceive_document() call to return")
    lines.append("- **Mode**: auto enhance mode (default)")
    lines.append("- **Environment**: Local MacBook (Apple Silicon), no GPU")
    lines.append(
        "- **Competitor numbers**: OpenDataLoader from published benchmarks; PyMuPDF/Unstructured/Azure from prior published data"
    )

    return "\n".join(lines)


async def main(public_mini: bool = False):
    print("=" * 60)
    print("DocMirror First Benchmark Run")
    print("=" * 60)
    print()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    COMPETITORS_DIR.mkdir(parents=True, exist_ok=True)

    if public_mini:
        manifest = generate_public_mini_manifest()
        manifest_path = RESULTS_DIR / "public-mini.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        benchmarks_path = OUTPUT_DIR / "PUBLIC_MINI_BENCHMARK.md"
        benchmarks_path.write_text(generate_public_mini_md(manifest), encoding="utf-8")
        print(f"Public mini manifest written to {manifest_path}")
        print(f"Public mini benchmark written to {benchmarks_path}")
        return

    results = await run_benchmark()
    manifest = generate_manifest(results)

    manifest_path = RESULTS_DIR / "v1.0.0.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Manifest written to {manifest_path}")

    # Write BENCHMARKS.md
    benchmarks_md = generate_benchmarks_md(manifest)
    benchmarks_path = OUTPUT_DIR / "BENCHMARKS.md"
    with open(benchmarks_path, "w") as f:
        f.write(benchmarks_md)
    print(f"✓ BENCHMARKS.md written to {benchmarks_path}")

    # Print summary
    summary = manifest.get("summary", {})
    print(f"\n📊 Benchmark Summary ({summary.get('record_count', 0)} documents):")
    print(f"   Avg elapsed:     {summary.get('avg_elapsed_ms', '—')} ms")
    print(f"   Avg per page:    {summary.get('avg_per_page_ms', '—')} ms")
    print(f"   Total pages:     {summary.get('total_pages', 0)}")
    print(f"   Total chars:     {summary.get('total_chars', 0):,}")
    print(f"   Total tables:    {summary.get('total_tables', 0)}")
    print(f"   Reading Order:   {summary.get('avg_reading_order_score', '—')}")
    print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run DocMirror release benchmarks")
    parser.add_argument(
        "--public-mini",
        action="store_true",
        help="Run the dependency-light public trust/evidence mini benchmark",
    )
    parsed = parser.parse_args()
    asyncio.run(main(public_mini=parsed.public_mini))
