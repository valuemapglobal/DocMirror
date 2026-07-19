# DocMirror

[English](README.md) | [Chinese](README_zh-CN.md)

**The open-source Commercial Document Trust Layer for RAG, agents, audit, and structured extraction.**
**Parse. Prove. Trust.**

DocMirror turns commercial documents into verifiable, audit-ready, machine-usable signals. It is built for documents that move money, create obligations, prove identity, support compliance, or feed risk systems.

It does not just parse a document. It tells you what it found, where it came from, and whether you should trust it.

## Why DocMirror

Most document tools stop at text, tables, or Markdown. DocMirror is designed for fields that may enter downstream systems, so every important output should carry evidence and quality context.

| Need | DocMirror output |
|---|---|
| Structured facts | `001_community.json` with the routed Community 6+1 structured output |
| Field evidence | source refs, page numbers, bounding boxes, raw values, and traces |
| Review decisions | quality status, confidence, warnings, and `needs_review` markers |
| RAG and agent input | Markdown and structure-aware chunk JSON with source context |
| Audit/debug handoff | optional `_mirror.json`, evidence bundle, quality report, manifest, and visual debug artifact |

DocMirror is not a generic OCR tool and not a generic RAG loader. Its category is narrower and sharper: **Commercial Document Trust Layer**.

## Install

```bash
pip install docmirror
docmirror doctor
```

Install only the public capabilities you need:

```bash
pip install "docmirror[pdf]"      # digital PDF support
pip install "docmirror[ocr]"      # scanned document OCR
pip install "docmirror[office]"   # DOCX/XLSX/PPTX
pip install "docmirror[server]"   # HTTP API
pip install "docmirror[all]"      # all public OSS extras
```

Commercial Enterprise and Finance extensions are distributed separately and are not required for the open-source package.

## 10-Minute Trusted Parse

Run the dependency-light public trust quickstart from a local checkout:

```bash
git clone https://github.com/valuemapglobal/DocMirror.git
cd DocMirror
python3 examples/trust_quickstart.py
```

You should see a synthetic commercial invoice with field evidence:

```text
DocMirror trust quickstart
document=synthetic_invoice_001 type=commercial_invoice
trust=confidence:0.96 evidence_coverage:1.00 review_required:true
field=invoice_number value=INV-2026-001 confidence=0.99 page=1 bbox=[88, 112, 236, 132] source_ref=synthetic_invoice_001#page=1&bbox=88,112,236,132 status=ok
```

Parse your own document. Community JSON is the default output:

```bash
pip install "docmirror[pdf,ocr,office]"
docmirror statement.pdf --output-dir ./output
```

Request the canonical Mirror alone with `--mirror`, or use the public quickstart
profile when you need diagnostics, audit evidence, and support artifacts:

```bash
docmirror statement.pdf --mirror
docmirror statement.pdf --profile quickstart
```

Scanned OCR uses deterministic safe correction by default. Use
`--ocr-correction suggest` to audit candidates without changing output, or
`--ocr-correction off` to keep normalization-only behavior.
Locale-aware correction packs can be selected with `--ocr-language`,
`--ocr-country`, `--ocr-locale`, and repeatable `--ocr-correction-pack` flags.
Maintain packs without parsing a document:

```bash
docmirror ocr-correction validate
docmirror ocr-correction list-packs
docmirror ocr-correction explain "Micros0ft" --language en --role text_line
docmirror ocr-correction evaluate ./tests/fixtures/ocr_correction --fail-on-regression
```

Project or customer packs can be loaded from paths listed in
`DOCMIRROR_OCR_CORRECTION_PACKS` (platform path separator). Opt-in packs set
`opt_in: true` and are enabled per request by pack id. Original OCR evidence is
always retained; pack id, version, locale, candidates, and decision margin are
recorded in the correction audit.

Default output:

```text
output/<run_id>/
  001_community.json
```

Community `6+1` is consumer-ready rather than a thin field/table dump. The six
core domains (bank statements, WeChat Pay, Alipay, VAT invoices, business
licenses, and credit reports) plus the universal fallback consistently expose:

- `business` for an immediate summary, key metrics, and genuinely derived periods, rankings, and reconciliations;
- `quality` for a scored `ready / review / insufficient` decision, operational issues, and evidence coverage;
- `data.field_details` for value references, confidence, source refs, review state, and raw text only when it differs from the canonical field value;
- `data.datasets` for JSON Pointer discovery of transaction, invoice, credit, and generic datasets without copying rows;
- `data.data_dictionary` for field/dataset labels, types, formats, masking policy, coverage, and nullability;
- `validation.domain_contract` for an honest domain-contract pass/partial result;
- `projection_lineage` for compact traceability back to Mirror facts and evidence.

Persisted Community artifacts use the compact 2.2 consumer contract and remain schema-readable alongside 2.0/2.1 payloads. The internal base DEC remains 2.0 and is upgraded atomically only after every required consumer block is complete. `data.fields` is the sole normalized-value location; intermediate field metadata, generic projections, and duplicate VAT aliases/base records are omitted after their information has been incorporated into references, datasets, and dictionaries. Single-plugin outputs use `plugin`; `plugins` is reserved for real compositions.
HTML and other presentation layers assemble their views from `document`, `business`, `quality`, `datasets`, and `data_dictionary`; UI layout is deliberately excluded from the core JSON contract.

Documents outside the six domains—and genuinely unclassified documents—still
run through the `generic` plugin. It adaptively recovers KV facts, typed and
normalized values, identity semantics, tables, outlines, and repeated row structures
when table geometry is unavailable; it no longer returns an empty success shell.

Diagnostic output with `--profile quickstart`:

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

## Python API

```python
import asyncio
from docmirror import perceive_document

async def main():
    result = await perceive_document("statement.pdf")
    mirror = result.to_mirror_json_vnext()

    print(mirror["mirror"]["schema_version"])
    print(mirror["document"].get("document_type"))
    print(mirror["quality"].get("overall", {}))

    for fact in mirror.get("semantics", {}).get("facts", []):
        evidence = fact.get("evidence") or {}
        print({
            "field": fact.get("field") or fact.get("name"),
            "value": fact.get("value"),
            "page": evidence.get("page"),
            "bbox": evidence.get("bbox"),
            "source_ref": evidence.get("source_ref"),
            "confidence": fact.get("confidence"),
            "needs_review": fact.get("needs_review", False),
        })

asyncio.run(main())
```

## Canonical Output Shape

DocMirror's mirror output is document-shaped and evidence-aware:

```json
{
  "mirror": {"schema": "docmirror.mirror_json", "schema_version": "1.0.7"},
  "source": {"filename": "statement.pdf"},
  "document": {"document_type": "bank_statement", "document_type_candidates": []},
  "pages": [],
  "evidence": {"text_atoms": [], "visual_atoms": []},
  "regions": [],
  "blocks": [],
  "graph": {},
  "semantics": {"facts": [], "entities": [], "views": {}},
  "quality": {"overall": {"status": "pass", "score": 1.0}},
  "diagnostics": {},
  "assets": {}
}
```

The key contract is simple: parsed fields should be accompanied by evidence and quality information, so downstream systems can decide whether to act, review, or reject.

## Common Workflows

### CLI

```bash
docmirror document.pdf
docmirror document.pdf --mirror --format markdown,chunks --debug-artifact
docmirror ./documents --recursive --output-dir ./output
docmirror plugins list
```

### API Server

```bash
pip install "docmirror[server]"
uvicorn docmirror.server.api:app --host 0.0.0.0 --port 8000
```

## Community, Enterprise, Finance

| Edition | Purpose |
|---|---|
| Community | Open-source trust layer, public domains, Mirror JSON, evidence, quality, CLI/API |
| Enterprise | Production batch processing, operations, private deployment, support, governance |
| Finance | Deep financial document extraction, cash-flow features, counterparty normalization, audit evidence |

The Community edition is not intentionally weakened. Mirror, Evidence, Quality Report, and visible failure behavior are core to the open-source standard.

## Known Limits

- OCR quality depends on scan quality and optional OCR dependencies.
- Complex merged tables and unusual reading order may require review.
- Some advanced commercial editions require separately distributed packages.

## Community

- Documentation: [valuemapglobal.github.io/DocMirror](https://valuemapglobal.github.io/DocMirror/)
- Quick Start: [docs/quickstart.md](docs/quickstart.md)
- Issues: [github.com/valuemapglobal/DocMirror/issues](https://github.com/valuemapglobal/DocMirror/issues)
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security: [SECURITY.md](SECURITY.md)

Created by **Adam Lin** and maintained by **ValueMap Global**. Licensed under Apache 2.0.
