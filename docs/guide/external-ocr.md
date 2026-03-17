# External OCR (Low-Quality Handoff)

When image quality is too poor for the built-in RapidOCR pipeline to reach your target recognition rate (e.g. 99%), you can delegate OCR to an external service (cloud API, high-end engine, or human review) and keep the rest of the pipeline unchanged.

## When Is Quality "Too Poor"?

DocMirror uses a **0–100 image quality score** derived from a Laplacian-variance blur metric (aligned with `PreAnalyzer`):

| Score range | Meaning | Built-in OCR |
|-------------|---------|--------------|
| 85–100 | Clear scan | Single-pass OCR sufficient |
| 60–84 | Medium | Standard multi-scale OCR |
| 40–59 | Low | Full enhancement pipeline; may still miss 99% target |
| **0–39** | **Very poor** | **Consider external OCR** (blur, low contrast, heavy noise, etc.) |

**Definition of "we cannot handle"**: when the **page/image quality is below `DOCMIRROR_EXTERNAL_OCR_QUALITY_THRESHOLD`** (default **80**). Below that, the engine treats the page as "too poor" for built-in OCR and, if an external provider is configured, sends the rendered image to that provider instead.

You can tune the threshold:

- **Stricter** (e.g. `50`): delegate more often; use external OCR for medium–low quality as well.
- **Looser** (e.g. `30`): delegate only for very bad scans; try built-in first on borderline images.

Quality is computed **before** running OCR (per page for PDF, per image for image files), so the handoff decision is fast and does not depend on recognition confidence.

## Configuring an External Provider

1. **Environment**

   ```bash
   export DOCMIRROR_EXTERNAL_OCR_QUALITY_THRESHOLD=80
   export DOCMIRROR_EXTERNAL_OCR_PROVIDER="myapp.ocr:call_cloud_ocr"
   ```

2. **Programmatic**

   ```python
   from docmirror.configs.settings import DocMirrorSettings

   settings = DocMirrorSettings(
       external_ocr_quality_threshold=80,
       external_ocr_provider="myapp.ocr:call_cloud_ocr",
   )
   ```

The provider is a **string** `"module:callable"` (e.g. `mypackage.ocr:run_ocr`). DocMirror will import the module and resolve the callable when needed.

## Provider Contract

Your callable will be invoked with:

- **Positional**: `image_bgr` — numpy array (BGR, OpenCV convention), full page or single image.
- **Keyword arguments**: `page_idx=0`, `dpi=200`, `min_confidence=0.3`, and any extra kwargs the pipeline may pass.

**Return value** — either:

1. **List of words** (recommended for simple integration):
   - `[(x0, y0, x1, y1, text, confidence), ...]`
   - Coordinates in **pixel space** of the input image. DocMirror will run table detection and layout grouping on top of this.

2. **Full result dict** (for providers that already do layout/table detection):
   - `content_type`: `"table"` or `"general"`.
   - For **table**: `header_text`, `footer_text`, `table` (list of rows, each row list of cell values).
   - For **general**: `lines` (list of `{"text": str, "bbox": (x0,y0,x1,y1)}`), `page_h`, `page_w`.
   - DocMirror will apply its OCR post-processing (amount/date/term correction) when `content_type == "table"`.

If the callable raises or returns `None`, the pipeline **falls back to built-in OCR** for that page/image.

## Example Implementation

```python
# myapp/ocr.py
import numpy as np

def call_cloud_ocr(image_bgr, *, page_idx=0, dpi=200, min_confidence=0.3, **kwargs):
    """Call your cloud OCR API; return list of words or full dict."""
    # e.g. encode image_bgr to PNG, POST to API, parse response
    words = your_api.recognize(image_bgr)  # list of (x0,y0,x1,y1,text,conf)
    return words
```

Then set `DOCMIRROR_EXTERNAL_OCR_PROVIDER=myapp.ocr:call_cloud_ocr`.

## Built-in: AI Studio Layout-Parsing API

DocMirror includes a ready-made provider for the **AI Studio layout-parsing** HTTP API. It sends the rendered page/image as base64 and returns the API’s markdown text as a single general-content block.

1. **Install the HTTP client**

   ```bash
   pip install docmirror[external-ocr]
   ```

   (The `ocr` extra is still required for image encoding and for built-in OCR fallback; use `docmirror[ocr,external-ocr]` if you use both.)

2. **Set environment variables**

   | Variable | Description |
   |----------|-------------|
   | `DOCMIRROR_EXTERNAL_OCR_PROVIDER` | `docmirror.core.ocr.aistudio_provider:call_aistudio_layout_ocr` |
   | `DOCMIRROR_EXTERNAL_OCR_QUALITY_THRESHOLD` | Optional; default `80`. Pages/images below this use the external API. |
   | `DOCMIRROR_AISTUDIO_OCR_API_URL` | Optional; default `https://j0g4k9d1a8x3mfx1.aistudio-app.com/layout-parsing` |
   | `DOCMIRROR_AISTUDIO_OCR_TOKEN` | **Required.** Bearer token for the API (`Authorization: token <TOKEN>`). |

   **方式一：使用项目自带的示例配置**

   ```bash
   cp .env.example .env
   # 编辑 .env，将 DOCMIRROR_AISTUDIO_OCR_TOKEN 改为你的 token（.env 已被 .gitignore，不会提交）
   set -a && source .env && set +a
   python3 -m docmirror your_image.jpg
   ```

   **方式二：直接 export**

   ```bash
   export DOCMIRROR_EXTERNAL_OCR_PROVIDER="docmirror.core.ocr.aistudio_provider:call_aistudio_layout_ocr"
   export DOCMIRROR_AISTUDIO_OCR_TOKEN="your-token-here"
   ```

3. **Behaviour**

   - The provider sends each low-quality page/image as a PNG (base64) with `fileType=1` (image). The API’s optional flags (`useDocOrientationClassify`, `useDocUnwarping`, `useChartRecognition`) default to `False` and can be overridden in code if you wrap the callable.
   - The response is parsed from `result["layoutParsingResults"]`; the markdown text from each result is concatenated and returned as one `"general"` block (single line with full text and full-page bbox). No table/header/footer splitting is done on the API response.
   - If the request fails or returns invalid JSON, the pipeline falls back to built-in OCR for that page/image.

## Where It Is Used

- **PDF**: For each page without a text layer (or with very little text), the extractor gets a per-page quality from pre-analysis. If `page_quality < external_ocr_threshold` and a provider is set, that page is sent to the external provider; otherwise built-in OCR runs.
- **Image files** (JPG/PNG/TIFF): Images are processed by the **same pipeline as PDF** (image → virtual single-page PDF → CoreExtractor). Quality is computed per page; if below threshold and provider is set, the page is sent to the external provider; otherwise built-in OCR runs.

## Output flow: unified with electronic document recognition

External OCR results are **merged into the same output flow** as electronic (digital) document recognition:

- **Same entry path**: Both image and PDF go through the same adapter (unified pipeline) and CoreExtractor. Images are converted to a single-page virtual PDF and then follow the same layout → extraction → merge → post-process path.
- **Same output shape**: Result is always a `BaseResult` with `pages` (each `PageLayout` with `blocks`: text, table, key_value, etc.), `full_text`, and metadata (e.g. `table_count`, `extraction_quality`, `scanned_pages`). Downstream (middlewares, API, builder) see one consistent structure whether the content came from digital text, built-in OCR, or external OCR.
- **Same post-processing**: Table blocks from external OCR (e.g. AI Studio markdown/table) are produced by the same `_extract_scanned_page` path that builds header/table/footer blocks and runs OCR post-processing; they then go through cross-page merge and table post-processing like electronic-document tables.

**HTML parsing before output**: The AI Studio API returns content in **HTML** (e.g. `markdown.text` contains `<table>…</table>`). The pipeline **parses this HTML** and then writes only structured/plain content into the comprehensive result:

- **Tables** → Two-column HTML tables are parsed into a **key_value** block (`raw_content`: dict of key→value). Downstream can use `result.entities` or the block’s `raw_content` for forms, validation, or APIs.
- **Text** → Any HTML in the OCR text is stripped to **plain text** before being stored in text blocks, so the output does not contain raw HTML.
