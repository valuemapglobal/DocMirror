#!/usr/bin/env python3
"""DocMirror E2E Parsing Diagnostic — Full Pipeline Trace with JSON Output.

Usage:
    # Parse a specific file
    python scripts/docmirror_diagnostic.py /path/to/file.pdf

    # Parse multiple files
    python scripts/docmirror_diagnostic.py file1.pdf file2.pdf

    # Parse all PDFs under tests/fixtures/ (default)
    python scripts/docmirror_diagnostic.py

    # Custom output directory
    python scripts/docmirror_diagnostic.py -o results/ file.pdf
"""
import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# Project root: scripts/ is one level below project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Logging: DocMirror at INFO, suppress noisy loggers
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logging.getLogger("docmirror").setLevel(logging.INFO)
logger = logging.getLogger("diagnostic")


def parse_args():
    parser = argparse.ArgumentParser(
        description="DocMirror E2E Parsing Diagnostic — trace pipeline & output JSON",
    )
    parser.add_argument(
        "files", nargs="*",
        help="PDF file(s) to parse. If omitted, scans all PDFs under tests/fixtures/",
    )
    parser.add_argument(
        "-o", "--output-dir", type=Path, default=PROJECT_ROOT / "output",
        help="Output directory for diagnostic JSON (default: output/)",
    )
    return parser.parse_args()


def collect_pdf_files(file_args: list) -> list[Path]:
    """Resolve file arguments to a list of PDF paths."""
    if file_args:
        paths = []
        for f in file_args:
            p = Path(f)
            if not p.is_absolute():
                p = Path.cwd() / p
            if not p.exists():
                print(f"⚠ File not found: {p}", file=sys.stderr)
                continue
            if p.is_dir():
                paths.extend(sorted(p.rglob("*.pdf")))
            else:
                paths.append(p)
        return paths

    # Default: all PDFs under tests/fixtures/
    fixtures_dir = PROJECT_ROOT / "tests" / "fixtures"
    if not fixtures_dir.exists():
        print(f"⚠ Fixtures directory not found: {fixtures_dir}", file=sys.stderr)
        return []
    pdfs = sorted(fixtures_dir.rglob("*.pdf"))
    print(f"📂 No files specified — scanning {fixtures_dir.relative_to(PROJECT_ROOT)}/")
    print(f"   Found {len(pdfs)} PDF file(s)\n")
    return pdfs


async def diagnose_one(pdf_path: Path, output_dir: Path) -> dict:
    """Run full diagnostic pipeline on a single PDF and save JSON."""
    import fitz

    # ── Phase 0: File info ──
    doc = fitz.open(str(pdf_path))
    num_pages = len(doc)
    p0 = doc[0]
    file_info = {
        "file_name": pdf_path.name,
        "file_path": str(pdf_path),
        "file_size_kb": round(pdf_path.stat().st_size / 1024, 1),
        "pages": num_pages,
        "page_width_pt": round(p0.rect.width),
        "page_height_pt": round(p0.rect.height),
        "page0_text_length": len(p0.get_text()),
    }
    doc.close()

    print(f"📄 {pdf_path.name} | {file_info['file_size_kb']}KB | {num_pages} pages")

    # ── Phase 1: PreAnalyzer ──
    t1 = time.time()
    from docmirror.core.extraction.pre_analyzer import PreAnalyzer
    doc = fitz.open(str(pdf_path))
    pre = PreAnalyzer().analyze(doc)
    doc.close()
    t1ms = (time.time() - t1) * 1000

    pre_analysis = {
        "time_ms": round(t1ms),
        "content_type": pre.content_type,
        "quality_score": pre.quality_score,
        "complexity_level": pre.complexity_level,
        "recommended_strategy": pre.recommended_strategy,
        "has_text_layer": pre.has_text_layer,
        "layout_homogeneous": pre.layout_homogeneous,
        "detected_language": pre.detected_language,
        "avg_image_quality": pre.avg_image_quality,
        "estimated_table_pages": pre.estimated_table_pages,
        "table_detection_cache_entries": len(pre.table_detection_cache),
        "strategy_params": pre.strategy_params,
    }
    print(f"  [PreAnalyzer] {t1ms:.0f}ms | type={pre.content_type} | homogeneous={pre.layout_homogeneous}")

    # ── Phase 2: CoreExtractor ──
    t2 = time.time()
    from docmirror.core.extraction.extractor import CoreExtractor
    base_result = await CoreExtractor().extract(pdf_path)
    t2ms = (time.time() - t2) * 1000

    extraction = {
        "time_ms": round(t2ms),
        "page_count": base_result.page_count,
        "total_blocks": len(base_result.all_blocks),
        "table_blocks": len(base_result.table_blocks),
        "full_text_length": len(base_result.full_text),
        "entities": base_result.entities,
    }
    print(f"  [Extractor]   {t2ms:.0f}ms | blocks={len(base_result.all_blocks)} tables={len(base_result.table_blocks)}")

    # Per-page breakdown
    pages_detail = []
    for pl in base_result.pages:
        block_types = {}
        for b in pl.blocks:
            block_types[b.block_type] = block_types.get(b.block_type, 0) + 1
        zones = {k: len(v) for k, v in pl.semantic_zones.items() if v}
        pages_detail.append({
            "page": pl.page_number,
            "is_scanned": pl.is_scanned,
            "block_count": len(pl.blocks),
            "block_types": block_types,
            "semantic_zones": zones,
        })
    extraction["pages"] = pages_detail

    # Table details
    tables_detail = []
    for i, tb in enumerate(base_result.table_blocks):
        raw = tb.raw_content
        if isinstance(raw, list) and raw:
            tbl_info = {
                "index": i + 1,
                "page": tb.page,
                "rows": len(raw),
                "cols": len(raw[0]) if raw[0] else 0,
                "header": raw[0],
                "data": raw[1:],
            }
        else:
            tbl_info = {
                "index": i + 1,
                "page": tb.page,
                "rows": 0,
                "cols": 0,
                "raw_type": type(raw).__name__,
            }
        tables_detail.append(tbl_info)
    extraction["tables"] = tables_detail
    extraction["full_text"] = base_result.full_text

    # ── Phase 3: Middleware Pipeline ──
    t3 = time.time()
    from docmirror.models.enhanced import EnhancedResult
    from docmirror.middlewares.base import MiddlewarePipeline
    from docmirror.middlewares.detection.scene_detector import SceneDetector
    from docmirror.middlewares.detection.language_detector import LanguageDetector
    from docmirror.middlewares.detection.institution_detector import InstitutionDetector

    enhanced = MiddlewarePipeline().execute(
        [SceneDetector(), LanguageDetector(), InstitutionDetector()],
        EnhancedResult(base_result=base_result),
    )
    t3ms = (time.time() - t3) * 1000

    middleware = {
        "time_ms": round(t3ms),
        "scene": enhanced.scene,
        "language": enhanced.enhanced_data.get("language"),
        "institution": enhanced.enhanced_data.get("institution"),
        "status": enhanced.status,
        "mutation_count": enhanced.mutation_count,
        "step_timings": enhanced.enhanced_data.get("step_timings", {}),
    }
    print(f"  [Middleware]  {t3ms:.0f}ms | scene={enhanced.scene} inst={enhanced.enhanced_data.get('institution')}")

    # ── Build output ──
    total_ms = t1ms + t2ms + t3ms
    total_rows = sum(len(b.raw_content) for b in base_result.table_blocks if isinstance(b.raw_content, list))

    result = {
        "file_info": file_info,
        "pre_analysis": pre_analysis,
        "extraction": extraction,
        "middleware": middleware,
        "summary": {
            "total_time_ms": round(total_ms),
            "time_per_page_ms": round(total_ms / max(num_pages, 1)),
            "pre_analyzer_ms": round(t1ms),
            "extraction_ms": round(t2ms),
            "middleware_ms": round(t3ms),
            "pages": num_pages,
            "tables": len(base_result.table_blocks),
            "total_rows": total_rows,
            "scene": enhanced.scene,
            "language": enhanced.enhanced_data.get("language"),
            "institution": enhanced.enhanced_data.get("institution"),
            "homogeneous": pre.layout_homogeneous,
            "content_type": pre.content_type,
        },
    }

    # ── Save to output directory ──
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{pdf_path.stem}_diagnostic.json"
    counter = 1
    while output_file.exists():
        output_file = output_dir / f"{pdf_path.stem}_diagnostic_{counter}.json"
        counter += 1

    output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"  💾 Saved → {output_file.relative_to(PROJECT_ROOT) if output_file.is_relative_to(PROJECT_ROOT) else output_file}")
    print()
    return result


async def main():
    args = parse_args()
    pdfs = collect_pdf_files(args.files)

    if not pdfs:
        print("No PDF files to process.", file=sys.stderr)
        sys.exit(1)

    summaries = []
    for pdf in pdfs:
        try:
            result = await diagnose_one(pdf, args.output_dir)
            summaries.append(result["summary"])
        except Exception as e:
            print(f"  ❌ FAILED: {e}\n")
            summaries.append({"file": pdf.name, "error": str(e)})

    # ── Final summary ──
    print("=" * 60)
    print(f"COMPLETED: {len(summaries)}/{len(pdfs)} files")
    total_time = sum(s.get("total_time_ms", 0) for s in summaries)
    total_tables = sum(s.get("tables", 0) for s in summaries)
    total_rows = sum(s.get("total_rows", 0) for s in summaries)
    print(f"Total time: {total_time:.0f}ms | Tables: {total_tables} | Rows: {total_rows}")
    errors = [s for s in summaries if "error" in s]
    if errors:
        print(f"Errors: {len(errors)}")
        for e in errors:
            print(f"  ❌ {e.get('file', '?')}: {e['error']}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
