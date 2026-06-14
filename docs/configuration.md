# Configuration

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCMIRROR_ENHANCE_MODE` | `standard` | Pipeline mode: `raw`, `standard` |
| `DOCMIRROR_MAX_PAGES` | `200` | Maximum pages to process |
| `DOCMIRROR_MAX_PAGE_CONCURRENCY` | `1` | Page-level concurrency: 1 = sequential; >1 enables parallel layout (process pool) and parallel digital-page extraction (thread pool). Use 2–4 for multi-page PDFs. |
| `DOCMIRROR_OCR_DPI` | `150` | OCR rendering resolution |
| `DOCMIRROR_FAIL_STRATEGY` | `skip` | Middleware error handling: `skip` (continue) or `abort` (halt pipeline) |
| `DOCMIRROR_LAYOUT_MAX_WORKERS` | *(none)* | When `max_page_concurrency` > 1, cap process count for parallel layout analysis. 0 = use `min(max_page_concurrency, cpu_count)`. |
| `DOCMIRROR_TABLE_RAPID_MAX_PAGES` | *(none)* | If set, skip RapidTable when document has more pages (saves ~10s/page). |
| `DOCMIRROR_TABLE_RAPID_MIN_CONFIDENCE_THRESHOLD` | `0.3` | Only try RapidTable when upstream table confidence is below this (0–1). |
| `DOCMIRROR_EXTERNAL_OCR_QUALITY_THRESHOLD` | `80` | When page/image quality (0–100) is **below** this, OCR is delegated to the external provider if set. See [External OCR](external-ocr.md). |
| `DOCMIRROR_EXTERNAL_OCR_PROVIDER` | *(none)* | Optional `module:callable` for external OCR (e.g. `docmirror.core.ocr.aistudio_provider:call_aistudio_layout_ocr`). Used when quality is below threshold. |
| `DOCMIRROR_AISTUDIO_OCR_API_URL` | *(default URL)* | AI Studio layout-parsing API endpoint (only when using the built-in aistudio provider). |
| `DOCMIRROR_AISTUDIO_OCR_TOKEN` | *(none)* | Bearer token for AI Studio API (required when using the built-in aistudio provider). |
| `DOCMIRROR_FORGERY_METADATA_BLACKLIST` | *(default list)* | JSON array of lowercase Creator/Producer terms to flag as suspicious; empty `[]` disables metadata forgery checks. |
| `DOCMIRROR_ENABLE_SLM` | *(none)* | When `1`, append `SLMEntityExtractor` to the middleware pipeline |
| `DOCMIRROR_IMAGE_OCR_ONLY` | *(none)* | When `1`, skip PDFAdapter for images and use ImageAdapter OCR directly |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API endpoint for VLM |
| `REDIS_URL` | *(none)* | Optional — only if you re-wire `framework/cache.py` into the dispatcher |

## Programmatic Configuration

```python
from docmirror.configs.runtime.settings import DocMirrorSettings

settings = DocMirrorSettings(
    default_enhance_mode="standard",
    max_pages=100,
    ocr_dpi=200,
)
```

## Enhancement Modes

| Mode | Middlewares | Use Case |
|------|-------------|----------|
| `raw` | None | Extraction only; no classification or entities |
| `standard` | Per-format pipeline (see below) | Default production parsing |
| `full` | Extended PDF pipeline where configured | Deeper table / language steps |

## Pipeline Configuration

Middleware pipelines are keyed by **content model** in `docmirror/configs/yaml/enhancement_profiles.yaml`.  
`docmirror/configs/pipeline/registry.py` delegates to those profiles.  
Class names must exist in `framework/orchestrator.py` → `MIDDLEWARE_REGISTRY`.

| Content model | `standard` middlewares |
|---------------|------------------------|
| `fixed_layout_rasterizable` (pdf, image, ofd) | EntityExtractor → EvidenceEngine → InstitutionDetector → Validator |
| `tabular_native` (excel, csv) | GenericEntityExtractor → EvidenceEngine |
| `markup_narrative` (word, ppt, email, web) | LanguageDetector → GenericEntityExtractor → EvidenceEngine |
| `interchange_structured` (json, xml, txt) | GenericEntityExtractor |
| `container` (archive) | *(empty — children enhanced individually)* |

Format routing (extension → adapter) is in `docmirror/configs/yaml/format_capabilities.yaml`.

`EvidenceEngine` performs 120-type document classification (replaces legacy SceneDetector).

## Observability and Logging Tracing

Component-isolated log labels:

- `[Server]`: API gateway lifecycle.
- `[Dispatcher]`: L0 validate, file-type routing, adapter dispatch.
- `[Orchestrator]`: Middleware pipeline supervision.
- `[Middleware]`: Per-step timing and mutations.
- `[EvidenceEngine]`: Classification evidence fusion.
- `[DI Container]`: Framework singleton initialization.
- `[PluginRegistry]`: Domain plugin loading.

## Parse Cache (optional, not on default path)

`framework/cache.py` provides Redis-backed caching when `REDIS_URL` is set, but **`ParserDispatcher` does not use it by default**. Finance/enterprise flows typically parse each file once.

- CLI `--skip-cache` and `PerceiveOptions.skip_cache` are retained for API compatibility (**no-op** today).
- To enable caching, wire `parse_cache.get/set` back into `dispatcher.py`.

See [Architecture](architecture.md).

## Table Extraction (RapidTable)

RapidTable is a vision-based table extractor (~10 s/page). It runs only when faster layers fail. You can skip it to reduce latency:

- **`DOCMIRROR_TABLE_RAPID_MAX_PAGES`**: e.g. `50` — documents with more than 50 pages will not use RapidTable on any page.
- **`DOCMIRROR_TABLE_RAPID_MIN_CONFIDENCE_THRESHOLD`**: e.g. `0.5` — if an earlier layer already returns confidence ≥ 0.5, RapidTable is not tried.

## Security and Forgery Detection

- **PDF/Image forgery** checks (metadata blacklist, ELA) are **for reference only** and do not constitute legal or compliance conclusions.
- **Metadata blacklist**: Override via `DOCMIRROR_FORGERY_METADATA_BLACKLIST`, a JSON array of lowercase strings (e.g. `["photoshop","acrobat"]`). Use `[]` to disable metadata-based forgery flags.

## CLI Options

```bash
python3 -m docmirror <file>                    # Parse a document
python3 -m docmirror --skip-cache <file>       # No-op (cache not on default path; kept for compat)
python3 -m docmirror --format json <file>      # Output format
python3 -m docmirror --no-save <file>          # Don't save to disk
python3 -m docmirror --output-dir ./out <file> # Custom output directory
python3 -m docmirror --authors                 # Show contributors
```
