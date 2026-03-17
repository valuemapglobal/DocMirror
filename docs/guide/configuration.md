# Configuration

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCMIRROR_ENHANCE_MODE` | `standard` | Pipeline mode: `raw`, `standard` |
| `DOCMIRROR_MAX_PAGES` | `200` | Maximum pages to process |
| `DOCMIRROR_MAX_PAGE_CONCURRENCY` | `1` | Page-level concurrency: 1 = sequential; >1 enables parallel layout (process pool) and parallel digital-page extraction (thread pool). Use 2–4 for multi-page PDFs. |
| `DOCMIRROR_OCR_DPI` | `150` | OCR rendering resolution |
| `DOCMIRROR_FAIL_STRATEGY` | `skip` | Error handling: `skip`, `raise`, `fallback` |
| `DOCMIRROR_LAYOUT_MAX_WORKERS` | *(none)* | When `max_page_concurrency` > 1, cap process count for parallel layout analysis. 0 = use `min(max_page_concurrency, cpu_count)`. |
| `DOCMIRROR_TABLE_RAPID_MAX_PAGES` | *(none)* | If set, skip RapidTable when document has more pages (saves ~10s/page). |
| `DOCMIRROR_TABLE_RAPID_MIN_CONFIDENCE_THRESHOLD` | `0.3` | Only try RapidTable when upstream table confidence is below this (0–1). |
| `DOCMIRROR_EXTERNAL_OCR_QUALITY_THRESHOLD` | `80` | When page/image quality (0–100) is **below** this, OCR is delegated to the external provider if set. See [External OCR](external-ocr.md). |
| `DOCMIRROR_EXTERNAL_OCR_PROVIDER` | *(none)* | Optional `module:callable` for external OCR (e.g. `docmirror.core.ocr.aistudio_provider:call_aistudio_layout_ocr`). Used when quality is below threshold. |
| `DOCMIRROR_AISTUDIO_OCR_API_URL` | *(default URL)* | AI Studio layout-parsing API endpoint (only when using the built-in aistudio provider). |
| `DOCMIRROR_AISTUDIO_OCR_TOKEN` | *(none)* | Bearer token for AI Studio API (required when using the built-in aistudio provider). |
| `DOCMIRROR_FORGERY_METADATA_BLACKLIST` | *(default list)* | JSON array of lowercase Creator/Producer terms to flag as suspicious; empty `[]` disables metadata forgery checks. |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL for parse result caching |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API endpoint for VLM |

## Programmatic Configuration

```python
from docmirror.configs.settings import DocMirrorSettings

settings = DocMirrorSettings(
    default_enhance_mode="standard",
    max_pages=100,
    ocr_dpi=200,
)
```

## Enhancement Modes

| Mode | Middlewares | Use Case |
|------|-----------|----------|
| `raw` | None | Fast preview, format conversion |
| `standard` | SceneDetector + EntityExtractor + InstitutionDetector + Validator | Production parsing with full entity extraction and trust scoring |

## Pipeline Configuration

The middleware pipeline is configured per-format in `docmirror/configs/pipeline_registry.py`:

| Format | `raw` | `standard` |
|--------|-------|-----------|
| PDF | — | SceneDetector → EntityExtractor → InstitutionDetector → Validator |
| Image | — | LanguageDetector → GenericEntityExtractor |
| Word | — | LanguageDetector → GenericEntityExtractor |
| Excel | — | GenericEntityExtractor |
| Other | — | LanguageDetector |

## Observability and Logging Tracing

DocMirror completely abandons generic standard output in favor of **Component-Isolated Contextual Tracing**.
Logs contain microsecond precision, Thread/Process mappings, and targeted subsystem labels:

- `[Server]`: Gateway latency and API lifecycle.
- `[Dispatcher]`: L0 Cache routing and payload inspection.
- `[Orchestrator]`: BaseResult mapping and overall Enhancement pipeline supervision.
- `[PluginRegistry]`: Dynamic domain module loading / collision monitoring.
- `[Merger]`, `[TableFix]`: Precise table anomaly resolution details.

## Cache Semantics

Parse results are cached by **content identity**, not by file path:

- Cache key = `checksum (SHA256) + document_type`. Same file content at different paths **shares the same cache entry**.
- To get different results for the same content (e.g. different tenants or sources), use a different `document_type` when calling the API, or disable caching for that flow.

See [Architecture](architecture.md) for the caching layer.

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
python3 -m docmirror --skip-cache <file>       # Force re-parse (skip Redis)
python3 -m docmirror --format json <file>      # Output format
python3 -m docmirror --no-save <file>          # Don't save to disk
python3 -m docmirror --output-dir ./out <file> # Custom output directory
python3 -m docmirror --authors                 # Show contributors
```
