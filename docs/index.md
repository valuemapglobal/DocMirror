# DocMirror

**The open-source Commercial Document Trust Layer for RAG, agents, audit, and structured extraction.**
**Parse. Prove. Trust.**

DocMirror turns commercial documents into verifiable, audit-ready, machine-usable signals. It is built for documents that move money, create obligations, prove identity, support compliance, or feed risk systems.

## What Makes It Different

DocMirror does not stop at OCR, raw text, or Markdown. It produces evidence-backed outputs that help downstream systems decide whether to act, review, or reject.

| Layer | Purpose |
|---|---|
| Mirror JSON | canonical document facts, structure, pages, blocks, entities |
| Evidence Bundle | source refs, page numbers, bounding boxes, raw values |
| Quality Report | quality status, confidence, warnings, review signals |
| Markdown / Chunks | RAG-ready reading-order content and retrievable chunks |
| Diagnostics | visible failure, partial-result context, artifact manifest |

## Start Here

```bash
pip install docmirror
docmirror doctor
```

Run the public trust quickstart from a local checkout:

```bash
python3 examples/trust_quickstart.py
```

Parse your own document:

```bash
pip install "docmirror[pdf,ocr,office]"
docmirror parse statement.pdf --format json,markdown,chunks --output-dir ./output --debug-artifact
```

## Product Promise

Every important field should be traceable to source text, page, geometry, confidence, and review status.

That means the first successful parse should answer:

```text
What was extracted?
Where did it come from?
How confident is DocMirror?
Does a human need to review it?
Can it enter a downstream system?
```

## Documentation Map

- [Installation](installation.md)
- [Quick Start](quickstart.md)
- [Development Manual (zh-CN)](development_manual_zh-CN.md)
- [Deployment](deployment.md)
- [API Authentication](api-authentication.md)

## Editions

| Edition | Purpose |
|---|---|
| Community | Open-source trust layer, public domains, Mirror JSON, evidence, quality, CLI/API |
| Enterprise | Production batch processing, operations, private deployment, support, governance |
| Finance | Deep financial document extraction, cash-flow features, counterparty normalization, audit evidence |

Community remains strong because Mirror, Evidence, Quality Report, and visible failure behavior are the open standard DocMirror is trying to establish.
