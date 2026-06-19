# DocMirror Hygiene Cleanup — Sprint 1 (completed)

## Done in this pass

| Item | Action |
|------|--------|
| vulture 100% (5) | Fixed — now **0** at 100% confidence |
| Dead CLI `--no-stage-output` | Removed (never wired) |
| `rapid_table_engine` | Dropped unused `RapidTableInput` import |
| `slm_entity_extractor` | Optional deps via `importlib.util.find_spec` |

### vulture 100% fixes

1. `docmirror/__main__.py` — removed unused `stage_output` parameter
2. `docmirror/cli/main.py` — removed `--no-stage-output` flag
3. `quality_router.py` — `zone_index` → `_zone_index`
4. `engine.py` — `zone_layer_hints` → `_zone_layer_hints`
5. `spatial_graph.py` — `syntactic_bridger` → `_syntactic_bridger`
6. `cross_page_predictor.py` — use `next_page_no` in debug log

## Deferred (next sprint)

Bulk `ruff --fix F401` on 139 files was attempted but **reverted** — it removed
re-exported symbols (`detect_merged_cells`, etc.) and broke imports.

### Recommended next steps (priority)

1. **Typing modernization** — file-by-file `Dict`/`Tuple` → `dict`/`tuple` with tests
2. **vulture 90%** — ~40 unused `Dict`/`Tuple` typing imports (safe batch per package)
3. **orphan_modules (60)** — triage plugin hooks → allowlist or wire imports
4. **ruff_strict ARG*** — unused callback parameters in middleware pipeline

Run: `python scripts/run_hygiene_audit.py --only vulture,ruff_strict`

---

## Sprint 2 — `core/analyze` + adjacent packages (completed)

### Packages cleaned (scoped `ruff --fix F401,UP035` only)

| Package | Fixes |
|---------|-------|
| `core/analyze` | 5 (removed unused `Dict`/`List`/`Tuple`/`Optional`) |
| `core/bridge` | 4 |
| `core/physical` | 5 |
| `core/extraction` | 10 |
| `core/entry` | 4 |
| `core/scene` | 8 |
| `framework` | 3 |
| `server` | 3 |

**Total: ~42 typing/import cleanups** in bounded packages (no whole-repo `--fix`).

### Tests

- `tests/smoke/test_quality_router.py` + `tests/test_quality_router.py`: **45 passed**
- Import smoke: `PreAnalyzer`, `extract_tables_layered`, `detect_merged_cells` OK

### Next (Sprint 3)

- `core/extract/` (careful — re-exports like `detect_merged_cells`)
- `core/ocr/` subpackages
- `classify_engine.py` commented code blocks (ERA001)

---

## Sprint 3 — `core/extract` + `core/ocr` + classify (completed)

| Area | Fixes |
|------|-------|
| `core/extract` | 31 ruff fixes + `best_candidate` dead `oracle` var |
| `core/extract/engine.py` | `detect_merged_cells` kept with `# noqa: F401` re-export |
| `core/ocr` | 45 ruff fixes + `start_y` / dead `flow` call removed |
| `cli/classify_engine.py` | removed unused `ClassificationRule` import |

### Tests

- `test_extraction_profile`, `test_cross_page_predictor`, `test_quality_router`: **43 passed**
- `test_page_token_ownership`, `test_scanned_local_structure`: run separately

### Next (Sprint 4)

- `core/extract/layers/` deep pass (if any remaining)
- `middlewares/` package (watch re-exports)
- ERA001 false positives in doc comments → tighten `commented_blocks` checker

---

## Sprint 4 — `middlewares` + `models` + checker tuning (completed)

| Area | Fixes |
|------|-------|
| `middlewares/` | 22 ruff fixes (typing imports) |
| `models/` | 17 ruff fixes + removed dead `annex_pages` in `serialization_contract` |
| `commented_blocks` checker | Skip CJK doc comments & `Level N:` section labels |

### Tests

- `test_mirror_serialization_contract`, `test_pec_contract`, `test_middleware_catalog`: to run in CI batch

### Next (Sprint 5)

- `adapters/` + `plugins/` (allowlist-heavy)
- `docmirror/cli/` remainder
- Optional: `--strict` hygiene gate in CI (non-blocking)

---

## Sprint 5 — `adapters` + `plugins` + `cli` + CI (completed)

| Area | Fixes |
|------|-------|
| `adapters/` + `cli/` | 18 ruff fixes |
| `plugins/` | 34 ruff fixes (`__init__.py` + `bank_compact_parser` star-import preserved) |

### CI

- New advisory job `hygiene` in `.github/workflows/ci.yml`
- Uploads `reports/hygiene_ci.json` + `.md` as artifact (`continue-on-error: true`)

### Tests

- `test_plugin_runner`, `test_generic_community_plugin`, `test_middleware_catalog`, `smoke/test_imports`: **45 passed**

### Next (Sprint 6)

- `docmirror/core/pipeline/` + `docmirror/core/table/`
- Tighten allowlist after orphan_modules triage
- Enable `--strict` gate when error count reaches zero
