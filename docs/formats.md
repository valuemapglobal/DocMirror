# Format Support

| Format | Adapter | Required Extra | Digital Text | OCR | Tables |
|--------|---------|---------------|:---:|:---:|:------:|
| PDF | `adapters.pdf` | `pdf` | ✅ | ✅ | ✅ |
| Image (JPG/PNG/TIFF) | `adapters.image` | `ocr` | — | ✅ | ✅ |
| Word (.docx) | `adapters.word` | `office` | ✅ | — | ✅ |
| Word (.doc, legacy) | `adapters.word` | `office` + LibreOffice | ✅ | — | ✅ |

**.doc (legacy)** support is optional: the system must have LibreOffice installed and `soffice` on PATH. Without it, parsing a .doc file returns a recoverable failure (`FORMAT_REQUIRES_CONVERTER`). Prefer .docx when possible.
| Excel (.xlsx) | `adapters.excel` | `office` | ✅ | — | ✅ |
| PowerPoint (.pptx) | `adapters.ppt` | `office` | ✅ | — | — |
| Email (.eml/.msg) | `adapters.email` | — | ✅ | — | — |
| HTML | `adapters.web` | — | ✅ | — | ✅ |
| JSON/XML/CSV | `adapters.structured` | — | ✅ | — | ✅ |
