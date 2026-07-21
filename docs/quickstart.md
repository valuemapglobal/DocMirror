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

The default CLI delivery is the three-part Community bundle:

```text
output/<run_id>/
  001_community.json
  001_content.md
  001_datasets/
    <dataset>.csv
    _audit_cells.csv
```

`docmirror document.pdf --all` additionally writes `001_mirror.json` and
`manifest.json`. The `001_content.md` bytes do not change between the two modes.

Start with these six blocks in `001_community.json`:

| Block | Purpose |
|---|---|
| `schema` | Bundle version, edition, domain, and support level |
| `document` | Source identity, language, page count, hash, and units |
| `sections` | Ordered semantic sections, items, groups, and dataset references |
| `datasets` | Complete records, counts, columns, completeness, and wide CSV references |
| `files` | Companion Markdown and Dataset Bundle paths |
| `warnings` | Lightweight actionable warnings |

The persisted artifact uses Community Bundle schema `3.0.0`. Each Dataset embeds
every record in `rows`; it is not a preview or pagination window. A record has a
stable `record_id`, `normalized`, `canonical_raw`, `raw`, and `source` object.
`row_count`, `completeness.emitted_row_count`, `len(rows)`, and the companion CSV
row count must agree. Markdown independently contains all parsed content and all
physical table rows. Each logical dataset is also written as a conventional wide
CSV under `001_datasets/`, while `_audit_cells.csv` preserves field-level evidence.

```json
{
  "name": "transactions",
  "primary_key": "record_id",
  "row_count": 1267,
  "completeness": {
    "expected_row_count": 1267,
    "emitted_row_count": 1267,
    "omitted_row_count": 0,
    "verified": true,
    "basis": "physical_payment_rows"
  },
  "rows": [
    {
      "record_id": "transactions:r000001",
      "normalized": {},
      "canonical_raw": {},
      "raw": {},
      "source": {"page_range": [1, 1]}
    }
  ]
}
```

The universal `generic` route is also used for `unknown` documents. It performs
text KV recovery, type inference, value normalization, identity discovery,
table/outline extraction, and conservative repeated-row recovery.

Licensed, installed Enterprise or Finance extensions are added automatically in
the full delivery. Output formats, editions, geometry, and Mirror detail are not
independent request parameters.

## 4. Inspect The Trust Artifacts

| Artifact | What to inspect |
|---|---|
| `001_mirror.json` | canonical source and diagnostic projection (`--all`) |
| `001_community.json` | Self-contained Community structured API payload |
| `001_content.md` | complete reading-order content and every table row |
| `001_datasets/` | one wide CSV per logical dataset plus `_audit_cells.csv` |
| `manifest.json` | artifact index, edition availability, and run status (`--all`) |

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
