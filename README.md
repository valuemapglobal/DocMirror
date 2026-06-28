# DocMirror

**The Trust Layer for Commercial Documents.**  
**Parse. Prove. Trust.**

Category: **Commercial Document Trust Layer**.

DocMirror turns commercial documents into verifiable, audit-ready, machine-usable signals. It is built for documents that move money, create obligations, prove identity, support compliance, or feed risk and audit systems.

DocMirror is not a generic OCR tool and not a generic RAG loader. Its core promise is stronger:

> Every important field should be traceable to source text, page, geometry, confidence, and review status.

## What It Does

- **Parse** commercial documents such as bank statements, invoices, receipts, contracts, IDs, licenses, tax forms, and payment records.
- **Prove** fields with source references, page numbers, bounding boxes, raw values, and transformation traces.
- **Trust** outputs with quality status, confidence, anomaly signals, partial-result handling, and `needs_review` markers.

## Install

```bash
pip install docmirror
```

Install optional capabilities as needed:

```bash
pip install "docmirror[pdf]"      # digital PDF support
pip install "docmirror[ocr]"      # scanned document OCR
pip install "docmirror[office]"   # DOCX/XLSX/PPTX
pip install "docmirror[server]"   # HTTP API
pip install "docmirror[all]"      # all public OSS extras
```

## Quick Start

```bash
docmirror --version
docmirror doctor
docmirror parse statement.pdf --format json --output-dir ./output
python examples/trust_quickstart.py
```

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

## Output Shape

DocMirror's canonical mirror output is document-shaped:

```json
{
  "mirror": {"schema": "docmirror.mirror_json", "schema_version": "3.0.0"},
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

The key design rule is simple: parsed fields should be accompanied by evidence and quality information, so downstream systems can decide whether to act, review, or reject.

## Supported Public Capabilities

| Capability | Install |
|---|---|
| Core API and CLI shell | `pip install docmirror` |
| Digital PDF | `pip install "docmirror[pdf]"` |
| Scanned OCR | `pip install "docmirror[ocr]"` |
| Office files | `pip install "docmirror[office]"` |
| Server API | `pip install "docmirror[server]"` |
| Public full stack | `pip install "docmirror[all]"` |

Commercial enterprise and finance extensions are distributed separately and are not required for the open-source package.

## Command Line

```bash
docmirror parse document.pdf --format json
docmirror parse ./documents --recursive --output-dir ./output
docmirror doctor
docmirror plugins list
```

## API Server

```bash
pip install "docmirror[server]"
uvicorn docmirror.server.api:app --host 0.0.0.0 --port 8000
```

## Known Limits

- OCR quality depends on scan quality and optional OCR dependencies.
- Complex merged tables and unusual reading order may require review.
- Some advanced commercial editions require separately distributed packages.
- Public benchmark claims are being moved to reproducible release gates before being advertised as fixed numbers.
- A dependency-light public mini benchmark is available via `python scripts/run_first_benchmark.py --public-mini`.

## Community

- Documentation: [valuemapglobal.github.io/docmirror](https://valuemapglobal.github.io/docmirror/)
- Issues: [github.com/valuemapglobal/docmirror/issues](https://github.com/valuemapglobal/docmirror/issues)
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security: [SECURITY.md](SECURITY.md)

Created by **Adam Lin** and maintained by **ValueMap Global**. Licensed under Apache 2.0.
