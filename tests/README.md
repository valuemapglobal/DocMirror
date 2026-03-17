# DocMirror Test Suite

This directory contains the comprehensive test suite for the **DocMirror** universal parsing engine. The engine achieves extremely high test coverage across unit tests, adapter functionality, validation models, and integration tests.

## Test Directory Structure

- `unit/`: Granular tests for individual layers of the Extract-Enhance pipeline.
  - `adapters/`: File format adapters (Word, Excel, PPT, etc.)
  - `layout/`: PDF routing and layout partitioning logic.
  - `middlewares/`: Security detection, entity matching, and metadata validation tests.
  - `table/`: `rapid_table`, clustering classifiers, and L0.5-L2 extraction tests.
- `benchmark/`: Performance testing utilities and regression benchmarking tools.
- `fixtures/`: Physical document samples required to execute the test suite. All files should be anonymized and legally scrubbed.
- Top-level files (`test_*.py`): Integration tests asserting end-to-end functionality such as the `docmirror/server` REST API, global plugin registry collision, setting configurations, and top-level `perceive_document()` integrations.

## Running the Tests

To run the entire test suite, execute the following from the root directory:

```bash
make test
```

Or run via pytest directly with warnings suppressed:

```bash
pytest tests/ -W ignore
```

## Creating New Tests

When contributing new parsers or extraction middlewares to DocMirror, ensure you:
1. Provide a relevant mocked fixture (do NOT provide PII or proprietary banking data).
2. Write an isolated `unit/` test focusing strictly on the function.
3. Hook into one of the broader E2E pipeline integration tests (`test_integration.py`).
