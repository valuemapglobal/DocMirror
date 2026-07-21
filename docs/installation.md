# Installation

## Base Install

```bash
pip install docmirror
```

The base package supports lightweight import, version checks, CLI help, and capability inspection:

```bash
python -c "import docmirror; print(docmirror.__version__)"
docmirror --help
docmirror doctor
```

## Public Extras

Install optional capabilities as needed:

| Extra | Packages | Use Case |
|---|---|---|
| `pdf` | PyMuPDF, pdfplumber | Digital PDF parsing |
| `ocr` | RapidOCR, OpenCV, NumPy | Scanned document OCR |
| `layout` | rapid-layout | Optional layout model support |
| `table` | rapid-table | Optional table model support |
| `formula` | rapid-latex-ocr | Formula recognition |
| `office` | python-docx, openpyxl, python-pptx | Word, Excel, PowerPoint |
| `security` | pikepdf | PDF inspection and tamper signals |
| `server` | fastapi, uvicorn, python-multipart | HTTP API server |
| `archive` | rarfile | Archive format support |
| `ai` | openai, google-generativeai | Optional AI/VLM integrations |
| `all` | Public OSS extras | Full public OSS feature set |
| `dev` | pytest, ruff, mypy, coverage, pre-commit | Development tools |
| `docs` | mkdocs-material, mkdocstrings | Documentation site |

Examples:

```bash
pip install "docmirror[pdf]"
pip install "docmirror[ocr]"
pip install "docmirror[office]"
pip install "docmirror[server]"
pip install "docmirror[all]"
```

## Commercial Extensions

Enterprise and finance extensions are distributed separately and are not part of the public `docmirror[all]` extra. They may require a private package index and a commercial license.

## Optional: Legacy `.doc` Support

Binary `.doc` files require LibreOffice and the `soffice` command on `PATH`. Without LibreOffice, DocMirror should return a recoverable feature-unavailable error and ask you to use `.docx` or install LibreOffice.

## Requirements

- Python 3.10+
- Linux, macOS, or Windows
