# Quick Start

DocMirror is the Commercial Document Trust Layer: **Parse. Prove. Trust.**

This guide is optimized for the first 10 minutes: install, inspect a trusted output shape, parse a real document, and know which artifacts to look at.

## 1. Run The Public Trust Quickstart

The fastest way to understand DocMirror does not require OCR models or private fixtures:

```bash
git clone https://github.com/valuemapglobal/docmirror.git
cd docmirror
python3 examples/trust_quickstart.py
```

Expected shape:

```text
DocMirror trust quickstart
document=synthetic_invoice_001 type=commercial_invoice
trust=confidence:0.96 evidence_coverage:1.00 review_required:true
field=invoice_number value=INV-2026-001 confidence=0.99 page=1 bbox=[88, 112, 236, 132] source_ref=synthetic_invoice_001#page=1&bbox=88,112,236,132 status=ok
```

The important part is not the sample value. It is the contract: field, value, confidence, page, bbox, source reference, and review status.

## 2. Install The Capabilities You Need

```bash
pip install docmirror
docmirror --version
docmirror doctor
```

Install public extras based on your input formats:

```bash
pip install "docmirror[pdf]"      # digital PDFs
pip install "docmirror[ocr]"      # scanned documents
pip install "docmirror[office]"   # Word, Excel, PowerPoint
pip install "docmirror[server]"   # FastAPI server
pip install "docmirror[all]"      # all public OSS extras
```

## 3. Parse A Commercial Document

```bash
docmirror statement.pdf --output-dir ./output
```

Community JSON is the default and only persisted document projection:

```text
output/<run_id>/
  001_community.json
```

Add the canonical Mirror alone with `--mirror`, or select the public quickstart
profile for review, diagnostics, demos, issues, or audit handoff:

```bash
docmirror statement.pdf --mirror
docmirror statement.pdf --profile quickstart
```

Diagnostic output:

```text
output/<run_id>/
  001_mirror.json
  001_community.json
  005_evidence_bundle.json
  output.md
  quality_report.json
  visual_debug.html
  manifest.json
```

## 4. Inspect The Trust Artifacts

| Artifact | What to inspect |
|---|---|
| `001_mirror.json` | optional canonical diagnostic projection requested with `--mirror` |
| `001_community.json` | community edition structured output |
| `001.md` / `output.md` | reading-order text for humans and LLM workflows |
| `001.chunks.json` | structure-aware chunks for retrieval pipelines |
| `005_evidence_bundle.json` | source refs, bbox, evidence links, support data |
| `quality_report.json` | quality gates, warnings, readiness, review signals |
| `visual_debug.html` | visual evidence overlay for review and demos |
| `manifest.json` | artifact index, edition availability, parse control fingerprint |

The Aha Moment is when you can answer:

```text
What did DocMirror extract?
Where did each important value come from?
Is the output trusted, partial, or review-required?
Can this artifact enter a downstream system?
```

## 5. Python API

```python
import asyncio
from docmirror import perceive_document

async def main():
    result = await perceive_document("statement.pdf")
    mirror = result.to_mirror_json_vnext()

    print("schema:", mirror["mirror"]["schema_version"])
    print("document:", mirror["document"].get("document_type"))
    print("quality:", mirror["quality"].get("overall", {}))

    for fact in mirror.get("semantics", {}).get("facts", []):
        evidence = fact.get("evidence") or {}
        print(
            fact.get("field") or fact.get("name"),
            fact.get("value"),
            evidence.get("page"),
            evidence.get("bbox"),
            evidence.get("source_ref"),
            fact.get("confidence"),
            fact.get("needs_review", False),
        )

asyncio.run(main())
```

## 6. Batch Parse

```bash
docmirror ./documents \
  --recursive \
  --output-dir ./output
```

For production batch queues, monitoring, and team workflows, use the separately distributed Enterprise edition.

## 7. Server

```bash
pip install "docmirror[server]"
uvicorn docmirror.server.api:app --host 0.0.0.0 --port 8000
```

## 8. Next Steps

- Use the [GitHub README](https://github.com/valuemapglobal/docmirror#readme) for the public landing page and positioning.
- Use GitHub Issues with a redacted sample or diagnostic bundle when DocMirror fails visibly.
