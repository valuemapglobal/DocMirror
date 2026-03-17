# Testing (G2)

DocMirror uses a **layered test** strategy so that unit tests stay fast and integration/golden tests cover real pipelines.

## Layers

| Layer | Location | Purpose |
|-------|----------|---------|
| **L1 Unit** | `tests/unit/` | Per-module tests with minimal dependencies: error codes, table classifier helpers, single middlewares, single adapters. No full PDF/Office parsing unless using tiny fixtures. |
| **L2 Integration** | `tests/test_e2e_parse.py`, `tests/test_integration.py` | Full pipeline: Dispatcher → Adapter → Orchestrator → PerceptionResult. Use fixtures under `tests/fixtures/`. |
| **L3 Golden** | `tests/golden/` | Regression: real samples + `expected.json` (or `expected.yaml`) with assertions (e.g. `table_count.min`, `entities_required`). See `tests/golden/README.md`. |

## Running tests

```bash
# All tests
pytest tests/ -v

# Unit only (fast)
pytest tests/unit/ -v

# Exclude slow / golden (if marked)
pytest tests/ -v -m "not slow"
```

## Adding tests

- **New unit test**: Add a file under `tests/unit/` (e.g. `tests/unit/table/test_engine.py`) or under `tests/unit/middlewares/`, `tests/unit/adapters/`. Prefer small, deterministic inputs (e.g. lists of lists for table confidence).
- **New golden sample**: Add the document and `expected.json` under `tests/golden/<format>/` and extend the golden test runner to include that path. See `tests/golden/README.md` for the expected schema.
- **Performance / concurrency**: Mark with `@pytest.mark.slow` and run only in CI cron or on demand so default `pytest tests/` stays quick.

## Coverage

- Aim for at least one unit test per table extraction layer (e.g. classifier, engine helpers), per middleware (e.g. Validator), and per adapter (e.g. WordAdapter) so that refactors are caught early.
- Golden tests are the source of truth for “does this real document still parse correctly?” and should be updated when intended behavior or sample files change.
