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
| Structured facts | `001_mirror.json` with document structure, facts, entities, and pages |
| Field evidence | source refs, page numbers, bounding boxes, raw values, and traces |
| Review decisions | quality status, confidence, warnings, and `needs_review` markers |
| RAG and agent input | Markdown and structure-aware chunk JSON with source context |
| Audit/debug handoff | evidence bundle, quality report, manifest, and visual debug artifact |

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
git clone https://github.com/valuemapglobal/docmirror.git
cd docmirror
python3 examples/trust_quickstart.py
```

You should see a synthetic commercial invoice with field evidence:

```text
DocMirror trust quickstart
document=synthetic_invoice_001 type=commercial_invoice
trust=confidence:0.96 evidence_coverage:1.00 review_required:true
field=invoice_number value=INV-2026-001 confidence=0.99 page=1 bbox=[88, 112, 236, 132] source_ref=synthetic_invoice_001#page=1&bbox=88,112,236,132 status=ok
```

Parse your own document:

```bash
pip install "docmirror[pdf,ocr,office]"
docmirror parse statement.pdf \
  --format json,markdown,chunks \
  --output-dir ./output \
  --debug-artifact
```

Typical output:

```text
output/<run_id>/
  001_mirror.json
  001_community.json
  001.md
  001.chunks.json
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
  "mirror": {"schema": "docmirror.mirror_json", "schema_version": "1.0.1"},
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
docmirror parse document.pdf --format json
docmirror parse document.pdf --format json,markdown,chunks --debug-artifact
docmirror parse ./documents --recursive --output-dir ./output
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

- Documentation: [valuemapglobal.github.io/docmirror](https://valuemapglobal.github.io/docmirror/)
- Quick Start: [docs/quickstart.md](docs/quickstart.md)
- Issues: [github.com/valuemapglobal/docmirror/issues](https://github.com/valuemapglobal/docmirror/issues)
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security: [SECURITY.md](SECURITY.md)

Created by **Adam Lin** and maintained by **ValueMap Global**. Licensed under Apache 2.0.
