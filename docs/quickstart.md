# Quick Start

DocMirror is the Commercial Document Trust Layer: Parse. Prove. Trust.

## 1. Install

```bash
pip install docmirror
docmirror --version
docmirror doctor
```

Install only the capabilities you need:

```bash
pip install "docmirror[pdf]"
pip install "docmirror[ocr]"
pip install "docmirror[office]"
```

## 2. Parse A Commercial Document

```bash
docmirror parse statement.pdf --format json --output-dir ./output
```

The command writes mirror/evidence/trust outputs under `./output`.

To inspect the public evidence/trust contract without private fixtures or OCR
models:

```bash
python examples/trust_quickstart.py
```

## 3. Python API

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

## 4. Output Layers

DocMirror outputs are designed for downstream systems:

```text
Mirror        facts and document structure
Evidence      page / bbox / source_ref / raw value
Trust Report  score / status / warnings / needs_review
Diagnostics   visible failure and partial-result context
```

## 5. Batch Parse

```bash
docmirror parse ./documents --recursive --format json --output-dir ./output
```

## 6. Server

```bash
pip install "docmirror[server]"
uvicorn docmirror.server.api:app --host 0.0.0.0 --port 8000
```

## 7. Public Mini Benchmark

```bash
python scripts/run_first_benchmark.py --public-mini
python scripts/generate_benchmark_table.py --public-mini
```
