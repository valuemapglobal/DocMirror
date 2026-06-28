# Contributing to DocMirror

Thank you for your interest in contributing to DocMirror! This guide will help you get started.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/valuemapglobal/DocMirror.git
cd DocMirror

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install with dev dependencies
pip install -e ".[dev,all]"

# Verify setup
pytest tests/smoke/ -v    # Quick smoke tests (no fixtures needed)
```

## Development Workflow

1. **Fork** the repository and create a feature branch:
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Make changes** — follow the coding standards below.

3. **Run checks** before committing:
   ```bash
   ruff check docmirror/          # Lint
   ruff format docmirror/         # Format
   pytest tests/smoke/ -v         # Quick smoke tests (no fixtures needed)
   pytest tests/unit/ -q -m "not tier_slow"  # Unit tests (most require no fixtures)
   python scripts/run_quality_gate.py --profile standard  # Quality gates
   ```

   > **Note on test fixtures**: `tests/fixtures/` and `tests/golden/` are gitignored
   > (private/sensitive real-world documents). If you need the full test suite,
   > contact the DocMirror team to request access. See `tests/README.md` for details.

4. **Commit** with [Conventional Commits](https://www.conventionalcommits.org/):
   ```
   feat: add new PDF table extraction strategy
   fix: correct column alignment for merged cells
   docs: update README with new configuration options
   chore: update dependencies
   ```

5. **Submit a Pull Request** against `main`.

## Coding Standards

- **Python 3.10+** — use modern syntax (`match/case`, `X | Y` unions)
- **Type hints** on all public functions
- **English** for all comments, docstrings, and variable names
- **Docstrings** in Google style for public API
- **Line length** — 120 characters max (enforced by ruff)

## Project Structure

```
docmirror/
├── core/             # Core extraction engines (CPS seven-stage pipeline)
│   ├── entry/        # perceive_document(), PerceiveOptions, PerceiveResult
│   ├── pipeline/     # DocumentPipeline, PagePipeline, PdfSyncProcessor
│   ├── table/        # Table Normalization Pipeline (TNP) — generic, ledger
│   ├── ocr/          # OCR pipeline (UOP) — RapidOCR + external fallback
│   ├── scene/        # EvidenceEngine — 120-type document classification
│   ├── extract/      # Core extraction from parsed pages
│   ├── segment/      # Page segmentation and layout
│   └── bridge/       # ParseResultBridge (Path B only)
├── adapters/         # Format-specific adapters
│   ├── pdf/          # PDF adapter with multi-strategy extraction
│   ├── image/        # Image adapter with OCR
│   ├── ofd/          # OFD (Chinese electronic invoice) adapter
│   ├── office/       # Word, Excel, PowerPoint adapters
│   ├── web/          # HTML and Email adapters
│   ├── data/         # Structured data (JSON, XML, CSV)
│   └── archive/      # Archive support (ZIP/RAR)
├── framework/        # Pipeline orchestration
│   ├── dispatcher.py  # L0 routing (FCR-driven)
│   ├── orchestrator.py # Middleware pipeline supervision
│   └── base.py        # BaseParser contract
├── middlewares/      # Enhancement pipeline steps (MEP platform)
│   ├── detection/    # EvidenceEngine, institution, language detection
│   ├── extraction/   # Entity extraction (bilingual, generic, SLM)
│   └── validation/   # Trust scoring, mutation analysis, anomaly detection
├── configs/          # YAML configuration
│   ├── yaml/         # FCR, enhancement profiles, middleware catalog, scene keywords
│   ├── runtime/      # DocMirrorSettings, env-backed configuration
│   └── pipeline/     # Registry and profile resolution
├── models/           # Data models
│   ├── entities/     # ParseResult (MOC), DomainExtractionResult (DEC)
│   └── construction/ # ParseResult bridge shims
├── plugins/          # Domain plugins
│   ├── community.py  # Community capability yaml + plugin discovery
│   ├── plugin_registry.py  # DomainPlugin ABC + registry singleton
│   ├── runner.py     # PEC extract runner
│   ├── bank_statement/  # Bank statement community plugin
│   ├── wechat_payment/  # WeChat payment community plugin
│   ├── alipay_payment/  # Alipay payment community plugin
│   ├── vat_invoice/     # VAT invoice community plugin
│   ├── business_license/ # Business license community plugin
│   ├── credit_report/   # Credit report community plugin
│   └── generic/     # Generic fallback plugin
├── cli/              # CLI entry point
├── server/           # FastAPI HTTP server
├── di/               # Service container (dispatcher, orchestrator, settings)
├── evidence/         # Security evidence ledger
├── security/         # Forgery detection, resource gates
├── quality/          # Quality gate infrastructure
├── features/         # Feature flag management
├── runtime/          # Runtime environment detection
└── scripts/          # CLI tooling (quality gates, validation, audit)
```

## Adding a New Adapter

1. Create `docmirror/adapters/your_format/your_format.py`
2. Subclass `BaseParser` from `docmirror.framework.base`
3. Implement `to_parse_result(file_path) -> ParseResult` (canonical format only)
4. Register in `docmirror/configs/yaml/format_capabilities.yaml`:
   - set `transport`, `content_model`, `extensions`, `binding.adapter`, `status: supported`
   - use `binding.transcode` if the adapter needs a converted canonical file
5. Run `python scripts/validate_format_capabilities.py`
6. Add tests in `tests/unit/` or `tests/`

## Adding a New Middleware (MEP)

Mirror-layer middleware is registered via **Middleware Execution Platform (MEP)** — not `orchestrator.py` dicts.

1. Create `docmirror/middlewares/your_category/your_middleware.py`
2. Subclass `BaseMiddleware` from `docmirror.middlewares.base`
3. Implement `process(result: ParseResult) -> ParseResult`
4. Add an entry to **`docmirror/configs/yaml/middleware_catalog.yaml`** (`module`, `class`, `stage`, optional `when` / `depends_on`)
5. Add the middleware name to **`docmirror/configs/yaml/enhancement_profiles.yaml`** under the appropriate `content_model` → `stages`
6. Run `python3 scripts/validate_middleware_catalog.py` and `python3 scripts/validate_format_capabilities.py`
7. Add tests in `tests/unit/`

Do **not** add middleware via decorators — use `middleware_catalog.yaml` only. Plugin logic belongs in `docmirror/plugins/runner.py`; post-extract hooks in `post_extract.yaml`.

## Reporting Issues

- Use [GitHub Issues](https://github.com/valuemapglobal/DocMirror/issues)
- Include: Python version, OS, DocMirror version, minimal reproduction steps
- For document parsing issues, include a sample file if possible (redact sensitive data)

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
