# DocMirror Test Suite

The TQG (Test Quality Gate Platform) architecture drives manifest-driven test gates.

## Layout (Design 10)

| Directory | Role | Tier |
|-----------|------|------|
| `unit/` | Component tests — mirror `docmirror/` source tree | Unit (unchanged) |
| `contract/` | MOC/PEC/DEC boundary invariants | `tier_contract` |
| `smoke/` | Imports, settings, plugin boot | `tier_smoke` |
| `regression/` | TQG manifest-driven gates | `tier_regression` |
| `e2e/` | CLI/API/full pipeline | `tier_e2e` + `tier_regression` |
| `integration/` | Legacy golden (dual-run with TQG) | `tier_regression` |
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

pytest tests/unit -q
pytest tests/regression -q -m "tier_regression and not tier_slow"
pytest tests/regression -m "tier_slow" -v   # nightly golden
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

## CI

- **PR** — `.github/workflows/ci.yml`: `tests/unit/` + `tier_smoke | tier_contract | tier_regression (not slow)`
- **Nightly** — `.github/workflows/nightly-golden.yml`: `tier_slow` extract + MEP golden
