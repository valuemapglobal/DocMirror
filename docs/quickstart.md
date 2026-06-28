# Quick Start

## Parse a PDF

```python
import asyncio
from docmirror import perceive_document

async def main():
    result = await perceive_document("statement.pdf")

    # Check status
    print(f"Status: {result.status}")
    print(f"Confidence: {result.confidence:.0%}")
    print(f"Scene: {result.scene}")  # "bank_statement", "invoice", etc.

    # Full text (Markdown format)
    print(result.content.text)

    # Iterate content blocks
    for block in result.content.blocks:
        if block.type == "table":
            print(f"Table: {block.table.headers}")
            for row in block.table.rows:
                print(f"  {row}")
        elif block.type == "key_value":
            for k, v in block.key_value.pairs.items():
                print(f"  {k}: {v}")

    # Domain-specific data (if detected)
    if result.domain:
        print(f"Domain: {result.domain.document_type}")

asyncio.run(main())
```

## Parse an Image

```python
result = await perceive_document("receipt.jpg")
print(result.content.text)  # OCR-extracted text
```

## CLI Usage

```bash
# Basic parse
python3 -m docmirror invoice.pdf

# Force re-parse (--skip-cache is a no-op; kept for API compatibility)
python3 -m docmirror --skip-cache invoice.pdf

# Don't save output to disk
python3 -m docmirror --no-save invoice.pdf
```

## Mirror Output Structure

`to_mirror_json_vnext()` returns the canonical document-shaped vNext mirror:

```json
{
  "mirror": {"schema_version": "3.0.0"},
  "source": {"filename": "invoice.pdf"},
  "document": {"document_type_candidates": []},
  "pages": [...],
  "evidence": {"text_atoms": [], "visual_atoms": []},
  "regions": [...],
  "blocks": [...],
  "graph": {"nodes": [], "edges": []},
  "semantics": {"entities": [], "facts": [], "views": {}},
  "quality": {"gates": []},
  "diagnostics": {"pipeline": []},
  "assets": {}
}
```

## Batch Processing

```python
from pathlib import Path

async def batch_parse(folder: str):
    for path in Path(folder).glob("*.pdf"):
        result = await perceive_document(str(path))
        print(f"{path.name}: {result.status}, {len(result.content.blocks)} blocks")
```

## Configuration via Environment

```bash
export DOCMIRROR_ENHANCE_MODE=standard
export DOCMIRROR_MAX_PAGES=100
export DOCMIRROR_OCR_DPI=200
```

## Output Files

Each `docmirror` command produces output files in `./output/` (configurable via `-o`):

```
output/
└── {task_id}/
    ├── 001_mirror.json        # Base parse result (mirror layer)
    └── 001_community.json     # Community plugin data (all 18 plugins merged)
```

- `task_id` = `{YYYYMMDD}_{HHMMSS}_{random4}` (e.g. `20260611_163000_a1b2`)
- `file_id` = `001` for single file, sequential for batch
- Enterprise edition adds `001_enterprise.json`

See [Architecture → Output File Naming](architecture.md#output-file-naming) for details.
