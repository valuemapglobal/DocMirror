# Contributing to DocMirror

Thank you for your interest in contributing to DocMirror! This guide will help you get started.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/valuemapglobal/docmirror.git
cd docmirror

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install with dev dependencies
pip install -e ".[dev,all]"

# Verify setup
pytest tests/ -v
```

## Development Workflow

1. **Fork** the repository and create a feature branch:
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Make changes** — follow the coding standards below.

3. **Run checks** before committing:
   ```bash
   ruff check docmirror/        # Lint
   ruff format docmirror/       # Format
   pytest tests/ -v             # Test (110 cases)
   ```

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
├── adapters/       # Format-specific adapters (PDF, Image, Office, ...)
│   ├── pdf/        # PDF adapter with multi-strategy extraction
│   ├── image/      # Image adapter with OCR
│   ├── office/     # Word, Excel, PowerPoint adapters
│   ├── web/        # HTML and Email adapters
│   └── data/       # Structured data (JSON, XML, CSV)
├── configs/        # Settings, pipeline registry, domain registry
├── core/           # Core engines
│   ├── extraction/ # Extraction, pre-analysis, quality routing
│   ├── layout/     # Layout analysis (DocLayout-YOLO, graph router)
│   ├── ocr/        # RapidOCR, formula recognition, seal detection
│   ├── table/      # Multi-strategy table extraction
│   ├── security/   # Forgery detection
│   └── output/     # Markdown export, visualization
├── framework/      # Dispatcher, orchestrator, base classes, optional cache
├── di/             # Service container (dispatcher / orchestrator singletons)
├── middlewares/    # Pipeline middlewares
│   ├── detection/  # Scene, institution, language detection
│   ├── extraction/ # Entity extraction
│   ├── alignment/  # Header alignment, amount splitting
│   └── validation/ # Trust scoring, mutation analysis
├── models/         # Data models (MOC / DEC)
│   ├── entities/   # ParseResult (MOC), DomainExtractionResult (DEC)
│   ├── construction/ # ParseResult bridge shims
│   └── tracking/   # Mutation tracking
├── plugins/        # Domain plugins (bank_statement, ...)
└── server/         # FastAPI server
```

## Adding a New Adapter

1. Create `docmirror/adapters/your_format/your_format.py`
2. Subclass `BaseParser` from `docmirror.framework.base`
3. Implement `to_parse_result(file_path) -> ParseResult` (canonical format only)
4. Register in `docmirror/configs/yaml/format_capabilities.yaml`:
   - set `transport`, `content_model`, `extensions`, `binding.adapter`, `status: supported`
   - use `binding.transcode` if the adapter needs a converted canonical file
5. Run `python tools/validate_format_capabilities.py`
6. Add tests in `tests/unit/` or `tests/`

## Adding a New Middleware (MEP)

Mirror-layer middleware is registered via **Middleware Execution Platform (MEP)** — not `orchestrator.py` dicts.

1. Create `docmirror/middlewares/your_category/your_middleware.py`
2. Subclass `BaseMiddleware` from `docmirror.middlewares.base`
3. Implement `process(result: ParseResult) -> ParseResult`
4. Add an entry to **`docmirror/configs/yaml/middleware_catalog.yaml`** (`module`, `class`, `stage`, optional `when` / `depends_on`)
5. Add the middleware name to **`docmirror/configs/yaml/enhancement_profiles.yaml`** under the appropriate `content_model` → `stages`
6. Run `python3 scripts/validate_middleware_catalog.py` and `python3 tools/validate_format_capabilities.py`
7. Add tests in `tests/unit/`

Do **not** add middleware via decorators — use `middleware_catalog.yaml` only. Plugin logic belongs in `docmirror/plugins/runner.py`; post-extract hooks in `post_extract.yaml`.

## Reporting Issues

- Use [GitHub Issues](https://github.com/valuemapglobal/docmirror/issues)
- Include: Python version, OS, DocMirror version, minimal reproduction steps
- For document parsing issues, include a sample file if possible (redact sensitive data)

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
