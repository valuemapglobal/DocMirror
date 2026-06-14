# Installation

## Basic Install

```bash
pip install docmirror
```

## With Format Support

Install only the extras you need:

```bash
# PDF parsing
pip install docmirror[pdf]

# OCR (for scanned documents)
pip install docmirror[ocr]

# Office formats (Word, Excel, PowerPoint)
pip install docmirror[office]

# Everything
pip install docmirror[all]
```

## Available Extras

| Extra | Packages | Use Case |
|-------|----------|----------|
| `pdf` | PyMuPDF, pdfplumber | Digital & scanned PDFs |
| `ocr` | RapidOCR, OpenCV | Scanned document text recognition |
| `layout` | rapid-layout | AI-powered layout analysis |
| `table` | rapid-table | Advanced table structure recognition |
| `formula` | rapid-latex-ocr | Mathematical formula recognition |
| `office` | python-docx, openpyxl, python-pptx | Word, Excel, PowerPoint |
| `security` | pikepdf | PDF forgery detection |
| `cache` | redis | Parse result caching |
| `langdetect` | fast-langdetect | Language detection |
| `all` | All of the above | Full installation |
| `dev` | pytest, ruff, mypy, coverage | Development tools |

## Optional: Legacy .doc Support

The **.doc** (binary Word) format is supported only when **LibreOffice** is installed and the `soffice` command is on your PATH. DocMirror uses it to convert .doc to a processable format.

- **Install LibreOffice**: [Download](https://www.libreoffice.org/download/) and install for your OS.
- **PATH**: Ensure `soffice` is available in the shell (e.g. `/usr/bin/soffice` on Linux, or add LibreOffice to PATH on Windows/macOS).

If you parse a .doc file without LibreOffice installed, DocMirror returns a failure with code `FORMAT_REQUIRES_CONVERTER` and `recoverable=True`; the message will ask you to install LibreOffice or use .docx.

## Requirements

- **Python**: 3.10+
- **OS**: Linux, macOS, Windows
