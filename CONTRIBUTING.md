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
├── input/            # File intake, adapters, parse control, extraction intake
├── structure/        # Evidence plane, page topology, OCR, tables, graph, verification
├── output/           # Canonical mirror JSON, projections, exporters, serialization
├── models/           # Shared contracts and typed data models
├── framework/        # Orchestration, dispatch, DI, middleware framework
├── runtime/          # Execution state, progress, artifacts, scheduling, checkpoint
├── plugins/          # Domain plugins plus internal plugin runtime
├── configs/          # Config loaders and packaged YAML/JSON schemas
├── evidence/         # Evidence bundles, ledgers, visual evidence
├── quality/          # Quality outcomes, gates, aggregation
├── security/         # Safety, redaction, egress, privacy, resource gates
├── features/         # Optional integrations such as RAG
├── eval/             # Evaluation and benchmark support
├── cli/              # Console commands
├── server/           # FastAPI and MCP serving boundaries
└── sdk/              # Python client/integration helpers
```

## Adding a New Adapter

1. Create `docmirror/input/adapters/your_format/your_format.py`
2. Subclass `BaseParser` from `docmirror.framework.base`
3. Implement `to_parse_result(file_path) -> ParseResult` (canonical format only)
4. Register in `docmirror/configs/yaml/format_capabilities.yaml`:
   - set `transport`, `content_model`, `extensions`, `binding.adapter`, `status: supported`
   - use `binding.transcode` if the adapter needs a converted canonical file
5. Run `python scripts/validate_format_capabilities.py`
6. Add tests in `tests/unit/` or `tests/`

## Adding a New Middleware (MEP)

Mirror-layer middleware is registered via **Middleware Execution Platform (MEP)** — not `orchestrator.py` dicts.

1. Create `docmirror/framework/middlewares/your_category/your_middleware.py`
2. Subclass `BaseMiddleware` from `docmirror.framework.middlewares.base`
3. Implement `process(result: ParseResult) -> ParseResult`
4. Add an entry to **`docmirror/configs/yaml/middleware_catalog.yaml`** (`module`, `class`, `stage`, optional `when` / `depends_on`)
5. Add the middleware name to **`docmirror/configs/yaml/enhancement_profiles.yaml`** under the appropriate `content_model` → `stages`
6. Run `python3 scripts/validate_middleware_catalog.py` and `python3 scripts/validate_format_capabilities.py`
7. Add tests in `tests/unit/`

Do **not** add middleware via decorators — use `middleware_catalog.yaml` only. Plugin runtime logic belongs under `docmirror/plugins/_runtime/`; post-extract hooks are declared in `post_extract.yaml`.

## Reporting Issues

- Use [GitHub Issues](https://github.com/valuemapglobal/DocMirror/issues)
- Include: Python version, OS, DocMirror version, minimal reproduction steps
- For document parsing issues, include a sample file if possible (redact sensitive data)

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
