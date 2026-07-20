# Quick Start

DocMirror is the Commercial Document Trust Layer: **Parse. Prove. Trust.**

This guide is optimized for the first 10 minutes: install, inspect a trusted output shape, parse a real document, and know which artifacts to look at.

## 1. Run The Public Trust Quickstart

The fastest way to understand DocMirror does not require OCR models or private fixtures:

```bash
git clone https://github.com/valuemapglobal/DocMirror.git
cd DocMirror
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

Mirror and Community JSON are persisted by default:

```text
output/<run_id>/
  001_mirror.json
  001_community.json
```

Start with these blocks in `001_community.json`:

| Block | Purpose |
|---|---|
| `business` | Human-readable business summary, key metrics, dimensions, and reconciliations |
| `quality` | Readiness, quality score, structured operational issues, normalization and evidence coverage |
| `data.field_details` | Canonical value refs, confidence, source refs, review state, and raw text only when different |
| `data.datasets` | Reference-only catalog for every consumer-visible row collection; rows are never copied |
| `data.data_dictionary` | Labels, types, formats, masking, coverage, and nullability for fields and dataset columns |
| `validation.domain_contract` | Community 6+1 contract pass/partial details |
| `projection_lineage` | Compact fact/evidence lineage |

The persisted artifact is Community schema `2.2`; the Schema also accepts 2.0/2.1 payloads. Base plugin envelopes remain `2.0` internally and are promoted only after the complete consumer projection has been generated. Single-plugin results use `plugin`; `plugins` is reserved for compositions.
Renderers derive HTML from the business, quality, field, dataset, dictionary, and lineage blocks; page-layout instructions are not part of Community JSON.

The universal `generic` route is also used for `unknown` documents. It performs
text KV recovery, type inference, value normalization, identity discovery,
table/outline extraction, and conservative repeated-row recovery.

Use `--community` when only the consumer projection is needed, `--all` for every
installed edition allowed by the active license, or `--audit` for review,
diagnostics, demos, issues, and audit handoff:

```bash
docmirror statement.pdf --community
docmirror statement.pdf --all
docmirror statement.pdf --audit
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
| `001_mirror.json` | canonical source and diagnostic projection written by default |
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

- Use the [GitHub README](https://github.com/valuemapglobal/DocMirror#readme) for the public landing page and positioning.
- Use GitHub Issues with a redacted sample or diagnostic bundle when DocMirror fails visibly.
