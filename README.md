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
| Structured facts | Community Bundle: semantic JSON, complete Markdown, and analysis-ready CSV |
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

Parse your own document. The CLI writes the three-part Community bundle by default;
use `--all` when Mirror and the manifest are also required:

```bash
pip install "docmirror[pdf,ocr,office]"
docmirror statement.pdf --output-dir ./output
docmirror statement.pdf --output-dir ./output --all
```

Enterprise and Finance projectors enforce package availability and entitlement at
their own invocation boundary; only successful projections are written.

Scanned OCR uses deterministic safe correction by default. Use
`--ocr-correction suggest` to audit candidates without changing output, or
`--ocr-correction off` to keep normalization-only behavior.
Locale-aware correction packs can be selected with `--ocr-language`,
`--ocr-country`, `--ocr-locale`, and repeatable `--ocr-correction-pack` flags.
Maintain packs without parsing a document:

```bash
docmirror ocr check
docmirror ocr packs
docmirror ocr explain "Micros0ft" --language en --role text_line
docmirror ocr eval ./tests/fixtures/ocr_correction --fail-on-regression
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
  001_content.md
  001_datasets/
    <dataset>.csv
    _audit_cells.csv
```

Community `6+1` uses Bundle schema 3.0. `001_community.json` is the self-contained
structured API payload with exactly `schema`, `document`, `sections`, `datasets`,
`files`, and `warnings`. Every Dataset embeds all records in `rows`, including
normalized values, canonical/source raw values, source evidence, and a stable
`record_id`; `completeness` makes omissions explicit.
`001_content.md` follows
[DMP 1.0](docs/markdown_profile_zh-CN.md) and contains the canonical reading flow
and every physical table row without derived dataset duplication or preview truncation.
`001_datasets/` contains a parallel conventional wide CSV per logical dataset:
one business record per row and one field per column. JSON and CSV use the same
ordered `record_id` set. `_audit_cells.csv` separately preserves field-level
normalized/raw values and evidence. Detailed quality and lineage remain available
through Mirror.

Documents outside the six domains—and genuinely unclassified documents—still
run through the `generic` plugin. It adaptively recovers KV facts, typed and
normalized values, identity semantics, tables, outlines, and repeated row structures
when table geometry is unavailable; it no longer returns an empty success shell.

## Python API

```python
from docmirror.sdk import DocMirrorClient

client = DocMirrorClient(output_dir="output")
task = client.parse("statement.pdf")
batch = client.parse_many(["statement.pdf", "license.png"])

print(task.status, task.task_id)
print(task.artifacts["community"])
print(batch.inputs)
```

The SDK, REST API, and task API return the same `TaskResult`. Public responses
contain artifact roles and quality/status summaries; they never return
`mirror.json` as the response body. Mirror remains an opt-in CLI diagnostic
artifact through `docmirror document.pdf --all`.

## Canonical Output Shape

DocMirror's internal/diagnostic mirror output is document-shaped and evidence-aware:

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
docmirror ./documents -r -j 8 -o ./output
docmirror plugins
```

### API Server

```bash
pip install "docmirror[server]"
uvicorn docmirror.server.api:app --host 0.0.0.0 --port 8000

# One or many files use the same task model
curl -F "file=@document.pdf" "http://localhost:8000/v1/tasks?wait=true"
curl -F "files=@one.pdf" -F "files=@two.png" "http://localhost:8000/v1/tasks"
```

## Community, Enterprise, Finance

| Edition | Purpose |
|---|---|
| Community | Open-source trust layer, public domains, evidence, quality, CLI/SDK/API |
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
