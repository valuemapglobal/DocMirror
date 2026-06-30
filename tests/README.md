# DocMirror Test Suite

> **Note on test data**: `tests/fixtures/` and `tests/golden/` are gitignored.
> They contain private/sensitive real-world documents and are **not** included
> in the public repository. See [Fixture Availability](#fixture-availability) below.

The TQG (Test Quality Gate Platform) architecture drives manifest-driven test gates.

## Layout (Design 10)

| Directory | Role | Tier |
|-----------|------|------|
| `unit/` | Component tests — mirror `docmirror/` source tree | Unit (unchanged) |
| `contract/` | MOC/PEC/DEC boundary invariants | `tier_contract` |
| `smoke/` | Imports, settings, plugin boot | `tier_smoke` |
| `regression/` | TQG manifest-driven gates | `tier_regression` |
| `e2e/` | CLI/API/full pipeline | `tier_e2e` + `tier_regression` |
| `integration/` | Frozen golden regression with TQG | `tier_regression` |
| `fixtures/` | Sample files + `registry.yaml` | — |
| `golden/` | Expected-output index (`manifest.json`) + per-track subdirs | — |


## TQG manifests (SSOT)

Gate cases live under `docmirror/configs/yaml/test/gates/`:

- `extract.yaml` — row preservation / oracle gates (+ `profiles` section for `GATE_PROFILES`)
- `classify.yaml` — `document_type` gates
- `mirror.yaml` — MEP mirror quality (from `mep_profiles.yaml`)
- `edition.yaml` — community/enterprise DEC gates
- `transport.yaml` — FCR format capability / dispatcher smoke gates
- `e2e.yaml` — four-file output and CLI contract gates

Classify case template: `gates/classify/_template.yaml` (reference only, not loaded by runner).


## Markers

| Marker | CI (PR) | Nightly |
|--------|---------|---------|
| `tier_smoke` | yes | yes |
| `tier_contract` | yes | yes |
| `tier_regression` (not `tier_slow`) | yes | yes |
| `tier_slow` | no | yes |
| `tier_benchmark` | no | opt-in |

Track markers: `track_extract`, `track_classify`, `track_mirror`, `track_edition`, `track_e2e`, `track_transport`.


## Running tests

```bash
make test                 # unit + PR tier matrix
make test-smoke           # tier_smoke only
make test-contract        # tier_contract only
make test-regression      # tier_regression, excludes slow
make test-golden          # tier_slow (5111 wechat, etc.)
make test-udtr-golden     # metadata-only UDTR golden manifest

pytest tests/unit -q
pytest tests/regression -q -m "tier_regression and not tier_slow"
pytest tests/regression -m "tier_slow" -v   # nightly golden
python3 scripts/validate/validate_udtr_golden.py tests/golden/udtr/manifest.example.json
```

TQG JSON reports are written to `artifacts/tqg/` when running regression tests.

## Adding a new document type

1. Add anonymized fixture under `fixtures/<type>/`
2. Register in `tests/fixtures/registry.yaml`
3. Add plugin + `scene_keywords` / classification rules
4. Add case to `configs/yaml/test/gates/classify.yaml` (and `extract.yaml` / `edition.yaml` if needed)
5. Run `python scripts/validate/validate_test_manifest.py` and `python scripts/validate/validate_dti.py`

No new `test_new_type_foo.py` required.

## Fixtures & Git LFS

`tests/fixtures/registry.yaml` manually maintained. Each asset records `size_bytes`; files ≥ **10 MB** are flagged `lfs: true` and `bytes: lfs_candidate` (migrate to Git LFS before commit). Current tree has no fixtures above the threshold (max ≈ 9.4 MB).

## Session hooks

`conftest.py` validates MEP catalog, post-extract catalog, and TQG manifest YAML at session start.

## Fixture Availability

`tests/fixtures/` and `tests/golden/` are **gitignored** — they contain private/sensitive
real-world documents that cannot be distributed publicly. When these directories are
missing or empty, tests that depend on them will be skipped with a clear message.

### Running tests without fixtures

The following test tiers do **not** require fixtures and will work on a fresh clone:

```bash
# Smoke tests — imports, settings, models, plugins (fastest)
make test-smoke
pytest tests/smoke/ -q

# Unit tests — most unit tests run without fixtures
pytest tests/unit/ -q -m "not tier_slow"

# Contract tests — mock-heavy boundary tests
pytest tests/contract/ -q -m "not tier_slow"
```

### Running tests with fixtures

To obtain the full test dataset, **contact the DocMirror team** or request access
via [GitHub Issues](https://github.com/valuemapglobal/docmirror/issues).

Once fixtures are available, all tiers can run:

```bash
# Full PR tier matrix
make test

# All tests including slow/nightly
pytest tests/ -v
```

### Adding new fixtures

If you contribute a new document type that requires a test fixture:

1. Create an anonymized sample under `tests/fixtures/<type>/`
2. Register in `tests/fixtures/registry.yaml`
3. Add golden expected output under `tests/golden/` if applicable
4. Ensure files ≥ 10 MB are marked `lfs: true`

## CI

- **PR** — `.github/workflows/ci.yml`: `tests/unit/` + `tier_smoke | tier_contract | tier_regression (not slow)`
- **Nightly** — `.github/workflows/nightly-golden.yml`: `tier_slow` extract + MEP golden + UDTR metadata-only golden

## UDTR Metadata-Only Golden

`tests/golden/udtr/manifest.example.json` is intentionally metadata-only: it stores
assertions about Mirror JSON output, not private source PDFs. Private cases can set
`private_source: true` or `skip_if_missing: true`; CI will skip them when the local
output is absent, while local/private runners can add `--strict-private` to enforce
the same manifest against generated outputs.
