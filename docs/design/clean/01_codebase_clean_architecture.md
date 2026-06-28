# DocMirror Clean Architecture Governance Plan

**Date:** 2026-06-28  
**Status:** Draft for implementation  
**Scope:** `docmirror/` package, tests, scripts, docs, CI, and public import contracts  
**Goal:** Build a single, general, durable cleanup system that can distinguish active code, dynamic entry points, compatibility APIs, obsolete code, and dead code without breaking supported scenarios.

---

## 0. Executive Conclusion

The current refactor successfully moved DocMirror away from the old `core/`, `adapters/`, `middlewares/`, `exporters/`, `integration/`, and `plugins.runner` layout into a clearer layered package:

```text
input -> structure -> output
framework/runtime/configs/models/evidence/quality/security
plugins/_runtime + plugins/domain packages
server/cli/sdk/features/eval
```

The remaining cleanup problem is not mainly "delete more files". It is a governance problem:

```text
The codebase no longer has a single machine-readable contract that says
which modules are public entry points, which are dynamic/plugin/config-loaded,
which old paths are intentionally compatible, and which modules are truly dead.
```

Without that contract, every large refactor will recreate the same failure pattern:

1. Runtime code moves successfully.
2. Tests, CI filters, docs, allowlists, and patch strings keep old paths.
3. Static orphan scans misclassify dynamic entry points.
4. Some real dead code hides inside allowlists.
5. Compatibility is accidental: either old paths silently disappear or never get removed.

The best long-term solution is a **Clean Architecture Manifest** plus enforcement:

```text
One manifest describes all valid module roles.
All import checks, orphan checks, compatibility checks, docs checks, CI path checks,
and deletion decisions consume the same manifest.
```

This turns cleanup from judgment-by-memory into a repeatable system.

---

## Execution Review — 2026-06-28

### Completed

- [已完成] P0 stale plugin patch paths migrated from `docmirror.plugins.runner` / `docmirror.plugins.licensing` to `docmirror.plugins._runtime.*`.
- [已完成] P0 `docmirror/__init__.py` package map updated to the current `input/structure/output/framework/runtime/plugins/...` layout.
- [已完成] P0 `scripts/code_hygiene/allowlist.yaml` stale paths migrated to `docmirror.plugins._runtime.post_extract.*` and `docmirror.output.exporters.sql_orm`.
- [已完成] P0 `.github/workflows/adaptive-routing-regression.yml` path filters moved off deleted `docmirror/core/**` paths.
- [已完成] P0 `.github/workflows/adaptive-routing-regression.yml` YAML/root indentation and inline Python indentation risk fixed.
- [已完成] P0 public/contributor docs updated where they pointed contributors to deleted adapter/middleware/plugin paths.
- [已完成] P0 import-linter contract rewritten for the post-core package layout.
- [已完成] P0 `scripts/validate/gate_pcm_legacy_refs.py` allowed paths updated to current `input/` and `structure/` paths.
- [已完成] Clean architecture manifest added at `docmirror/configs/architecture/clean_manifest.yaml`.
- [已完成] Manifest loader added at `scripts/code_hygiene/clean_manifest.py`.
- [已完成] Manifest validator added at `scripts/validate/validate_clean_manifest.py`.
- [已完成] Manifest validator checks required sections, live module paths, removed module paths, allowlist staleness, removed-path references, and workflow YAML parseability.
- [已完成] Manifest validation optimized to avoid runtime imports and to prune ignored/generated directories.
- [已完成] `scripts/code_hygiene/graph.py` now treats `mock.patch("docmirror...")` and `monkeypatch.setattr("docmirror...")` strings as import references.
- [已完成] `check_orphan_modules()` now consumes the clean manifest, so public/dynamic/quarantine modules are not misclassified as accidental orphans.
- [已完成] Removed-path contract test added at `tests/contract/test_removed_import_paths.py`.
- [已完成] `make validate-clean` added and `make lint` now runs clean manifest validation.
- [已完成] CI now runs `scripts/validate/validate_clean_manifest.py` in the Python 3.12 Ubuntu validation lane.
- [已完成] `.importlinter` is now generated from `clean_manifest.yaml` by `scripts/validate/generate_import_linter.py`.
- [已完成] Hand-written `pyproject.toml` import-linter contract removed; manifest-generated `.importlinter` is the single executable import contract.
- [已完成] `lint-imports --config .importlinter` is enforced in Makefile, CI, release gate, and contract tests.
- [已完成] Clean quarantine report added at `scripts/validate/report_clean_quarantine.py` with JSON output and overdue failure mode.
- [已完成] Dedicated clean architecture workflow added at `.github/workflows/clean-architecture.yml` with PR, push, scheduled, and manual execution.
- [已完成] All current orphan modules were individually classified with static/string/config/docs evidence.
- [已完成] Dead orphan modules with no liveness evidence were deleted; retained quarantine list is reduced to six active/transition modules with owner, reason, exit criteria, and review date.
- [已完成] High-confidence vulture findings fixed: unused imports and unreachable returns removed.
- [已完成] Focused validation passed:
  - `python3 -m compileall -q docmirror scripts/validate scripts/code_hygiene`
  - `python3 -m pytest tests/smoke/test_imports.py tests/unit/test_plugin_runner.py tests/unit/test_cli_license_show.py tests/unit/test_licensing_entitlements.py tests/unit/test_code_hygiene.py tests/contract/test_removed_import_paths.py -q` -> 50 passed
  - `python3 scripts/validate/validate_clean_manifest.py`
  - `python3 scripts/validate/generate_import_linter.py --check`
  - `python3 scripts/validate/report_clean_quarantine.py --fail-overdue`
  - `python3 -m vulture docmirror --min-confidence 80`
  - workflow YAML parse check

### Completed By Policy Decision

- [已完成] Compatibility decision made for old plugin internals: no alias retained for `docmirror.plugins.runner`, `docmirror.plugins.licensing`, or `docmirror.plugins.post_extract`; tests now use canonical `_runtime` paths.
- [已完成] Old internal package paths remain removed: `docmirror.core`, `docmirror.adapters`, `docmirror.middlewares`, `docmirror.exporters`, `docmirror.integration`, `docmirror.deployment`, `docmirror.di`.

### Remaining Follow-Up

- [已完成] Docs removed-path scanning exists for current docs/code; design-history docs intentionally remain allowed to mention old paths.
- [已完成] Layer-by-layer import contracts are generated from manifest and executed by import-linter; known historical direct couplings are explicit manifest exceptions with review dates.
- [待后续] Six retained quarantine modules remain active by evidence and must be reviewed by their manifest `review_by` dates.

### Completion Review

- [已完成] Phase 3 per-module disposition completed for current candidates: delete/no-delete decisions are represented in code and manifest.
- [已完成] Phase 4 delete-with-proof completed for safe candidates; active transition modules were retained instead of deleted.
- [已完成] Phase 5 quarantine expiry reporting implemented in CI and scheduled workflow.
- [已完成] Automatic generation of import-linter contracts from `clean_manifest.yaml` implemented and enforced with `--check`.

---

## 1. First-Principles Model

### 1.1 What Makes Code "Alive"

A program file is alive only if at least one of these is true:

| Liveness source | Meaning | Example |
|---|---|---|
| Static import | Imported by another active production module | `docmirror.input.entry.factory` |
| Public entry point | Invoked by package users, CLI, server, SDK, or `python -m` | `docmirror.__init__`, `docmirror.cli.main` |
| Config entry | Loaded from YAML/JSON/TOML as a module/class path | post-extract hooks |
| Plugin entry | Registered by plugin registry, entry point, or domain package import side effect | `community_plugin.py` |
| Reflection/API contract | Patched/imported by supported tests or downstream users by documented path | public compatibility aliases |
| Generated/artifact role | Consumed by packaging, schema validators, docs, CI, or build scripts | schema modules, exporters |
| Quarantine role | Intentionally retained but not active; has owner, expiry, and deletion criteria | transitional compatibility modules |

Anything else is either:

```text
dead code,
experimental code that should move outside the runtime package,
or future code that must be explicitly marked as planned/quarantined.
```

### 1.2 What Makes a Path "Public"

A Python module path is public only if it is one of:

1. Exported by `docmirror.__all__`.
2. Used in `pyproject.toml` entry points.
3. Documented in README/docs as importable.
4. Used by server/CLI/SDK as an external contract.
5. Listed in the clean manifest as a compatibility path.

Everything else is internal and may be moved, but internal moves must update:

- tests
- patch strings
- YAML module paths
- CI path filters
- hygiene allowlists
- docs and design references

### 1.3 The Only Safe Deletion Rule

A file can be deleted only when all are true:

```text
static_inbound_refs = 0
config_refs = 0
dynamic_manifest_refs = 0
public_contract_refs = 0
test_refs = 0, unless tests are obsolete and removed in the same change
docs_refs = 0, unless docs are updated in the same change
compatibility_window = expired or not applicable
```

If any condition is unknown, the file is not deleted. It is moved to an explicit quarantine list with an owner and expiry.

---

## 2. Target Architecture Contract

### 2.1 Canonical Package Layers

The canonical package architecture should be:

```text
docmirror
  __init__.py              public Python API
  __main__.py              python -m docmirror parse entry
  cli/                     console commands only
  server/                  HTTP/MCP serving boundary
  sdk/                     local Python client/integration helpers
  input/                   file intake, adapters, parse control, extraction intake
  structure/               evidence plane, page topology, OCR, tables, graph, verification
  output/                  canonical mirror, projections, exporters, serialization
  models/                  shared contracts and typed data models
  framework/               orchestration, dispatch, DI, middleware framework
  runtime/                 execution state, progress, artifacts, scheduling, checkpoint
  plugins/                 domain plugins and plugin runtime
  configs/                 config loaders and packaged YAML/JSON schemas
  evidence/                evidence bundles, ledgers, visual evidence
  quality/                 quality outcomes, gates, aggregation
  security/                safety, redaction, egress, privacy, resource gates
  features/                optional downstream integrations such as RAG
  eval/                    evaluation and benchmark support
  errors/                  error/result envelopes
```

The old layer names are not canonical:

```text
docmirror.core
docmirror.adapters
docmirror.middlewares
docmirror.exporters
docmirror.integration
docmirror.deployment
docmirror.di
docmirror.plugins.runner
docmirror.plugins.licensing
docmirror.plugins.post_extract
```

### 2.2 Compatibility Policy

There are two valid strategies. The project must choose one per old path family.

**Preferred strategy: no compatibility alias for internal paths**

Use this for old internals:

```text
docmirror.core.*
docmirror.adapters.*
docmirror.middlewares.*
docmirror.exporters.*
docmirror.integration.*
docmirror.deployment.*
docmirror.di.*
```

Action:

- Update tests, docs, scripts, CI, allowlists to canonical paths.
- Add an import-block test asserting these old paths do not import.
- Do not add alias packages.

**Temporary compatibility alias for historically public plugin paths**

Use this only if external users may have imported the old plugin runtime paths:

```text
docmirror.plugins.runner -> docmirror.plugins._runtime.runner
docmirror.plugins.licensing -> docmirror.plugins._runtime.licensing
docmirror.plugins.post_extract -> docmirror.plugins._runtime.post_extract
```

Action:

- Provide lightweight alias modules/packages that import lazily.
- Emit `DeprecationWarning` with a removal version.
- Add tests for both old and new imports.
- Add manifest expiry date/version.

If external compatibility is not required, do not add aliases. Update all tests to `_runtime` paths and add import-block tests for the old paths.

**Recommendation:** keep temporary aliases only for `docmirror.plugins.*` runtime paths for one minor release; do not keep aliases for `core`, `adapters`, `middlewares`, `exporters`, `integration`, `deployment`, or `di`.

---

## 3. Current Findings And Root Fixes

### 3.1 Broken Old Plugin Patch Paths

Observed broken imports:

```text
docmirror.plugins.runner
docmirror.plugins.licensing.offline
docmirror.plugins.licensing.online
docmirror.plugins.licensing.snapshot
docmirror.plugins.post_extract.hooks.credit_sections
```

Current tests still patch these paths:

```text
tests/unit/test_plugin_runner.py
tests/unit/test_cli_license_show.py
tests/integration/test_enterprise_bank_statement.py
tests/integration/test_finance_pec.py
tests/contract/test_pec_contract.py
docmirror/eval/tqg/licensing_exec.py
```

Root cause:

```text
The plugin runtime moved to docmirror.plugins._runtime, but mock/patch strings
were not treated as import contracts by the refactor tooling.
```

Best fix:

1. Decide compatibility policy.
2. If no compatibility: update every patch string to `_runtime`.
3. If compatibility: add alias modules and still migrate internal tests to `_runtime` so old paths are only tested in compatibility tests.
4. Extend hygiene scanning to parse `unittest.mock.patch("...")` strings as import references.

### 3.2 Stale Architecture Documentation

`docmirror/__init__.py` still describes old folders:

```text
core/
middlewares/
di/
adapters/
```

Root cause:

```text
Top-level package docstring is not validated against the architecture manifest.
```

Best fix:

- Replace it with canonical layer list.
- Add `scripts/validate/validate_architecture_manifest.py` to fail if public docs mention deleted canonical paths except inside migration/design-history sections.

### 3.3 Stale Hygiene Allowlist

Current allowlist still contains old paths:

```text
docmirror.plugins.post_extract.hooks.*
docmirror.exporters.sql_orm
```

Root cause:

```text
Allowlists are independent hand-written truth, not derived from actual module graph.
```

Best fix:

- Move allowlist intent into the clean manifest.
- Generate checker allowlists from manifest entries.
- Add a validator: every allowlist module path must import or be marked `removed`.

### 3.4 Stale CI Path Filters

`adaptive-routing-regression.yml` still watches:

```text
docmirror/core/pipeline/complexity/**
docmirror/core/pipeline/pipelines/**
docmirror/core/pipeline/page_pipeline.py
```

Root cause:

```text
CI filters are not tied to code ownership/layer declarations.
```

Best fix:

- Declare layer path globs in the clean manifest.
- Generate or validate workflow path filters against those globs.
- Add YAML parse validation for all workflows.

### 3.5 Static Orphan Ambiguity

The scan found modules with zero static inbound imports. Some are probably active dynamic endpoints; some are likely dead or future code.

High-confidence review candidates:

```text
docmirror.eval.structure_diff
docmirror.eval.structure_gate_metrics
docmirror.evidence.source_resolver
docmirror.input.extraction.html_utils
docmirror.models.mirror.typed_span
docmirror.models.serialization
docmirror.output.exporters.document_flow
docmirror.output.exporters.mathml
docmirror.output.exporters.pdfua_validation
docmirror.output.exporters.sql_orm
docmirror.plugins._base.header_normalizer
docmirror.runtime.checkpoint_writer
docmirror.structure.tables.grid_tensor
docmirror.structure.tables.page_state
docmirror.structure.ocr.formula_evidence
```

Root cause:

```text
The project has dynamic/plugin/config entry points, but the checker only partly
understands them; meanwhile some modules really are orphaned.
```

Best fix:

- Add manifest roles for `entry`, `plugin`, `config_loaded`, `exporter`, `schema`, `quarantine`, `internal`.
- Orphan checker consults manifest.
- All `quarantine` entries require an expiry and resolution.
- A module with role `internal` and zero inbound refs fails CI.

### 3.6 Files That Look Legacy But Are Still Active

These should not be deleted now:

```text
docmirror.models.mirror.legacy_project
docmirror.models.mirror.legacy_access
docmirror.structure.ocr.recognize.runner_legacy
docmirror.structure.ocr.preprocess.legacy_fallback
docmirror.structure.ocr.reconstruct.grid_legacy
```

They are still referenced by page canvas export, page topology, scanned OCR, fallback OCR, and tests.

Best fix:

- Rename only when replacing their role, not merely because the name contains `legacy`.
- Add manifest entries:

```yaml
role: active_internal
reason: "Active fallback implementation retained until gcr/scanned pipeline replaces it."
```

---

## 4. Clean Architecture Manifest

### 4.1 File

Create:

```text
docmirror/configs/architecture/clean_manifest.yaml
```

### 4.2 Schema

```yaml
version: 1

layers:
  input:
    paths:
      - docmirror/input/**
    allowed_imports:
      - docmirror.models
      - docmirror.configs
      - docmirror.runtime
      - docmirror.security
      - docmirror.structure
      - docmirror.output

  structure:
    paths:
      - docmirror/structure/**
    allowed_imports:
      - docmirror.models
      - docmirror.configs
      - docmirror.evidence
      - docmirror.quality
      - docmirror.security

  output:
    paths:
      - docmirror/output/**
    allowed_imports:
      - docmirror.models
      - docmirror.evidence
      - docmirror.quality
      - docmirror.configs

public_modules:
  - module: docmirror
    reason: Python API
  - module: docmirror.cli.main
    reason: console script
  - module: docmirror.__main__
    reason: python -m docmirror
  - module: docmirror.server.api
    reason: FastAPI app
  - module: docmirror.server.mcp
    reason: MCP server

dynamic_modules:
  - module: docmirror.plugins._runtime.post_extract.hooks.credit_sections
    source: docmirror/configs/yaml/post_extract.yaml
  - module: docmirror.plugins._runtime.post_extract.hooks.mirror_table_rebuild
    source: docmirror/configs/yaml/post_extract.yaml
  - module: docmirror.plugins._runtime.post_extract.hooks.trust_projection
    source: docmirror/configs/yaml/post_extract.yaml

compatibility_modules:
  - old: docmirror.plugins.runner
    new: docmirror.plugins._runtime.runner
    status: deprecated
    remove_after: "1.2.0"
    warning: "Use docmirror.plugins._runtime.runner"

removed_modules:
  - module: docmirror.core
    replacement: docmirror.structure
  - module: docmirror.adapters
    replacement: docmirror.input.adapters
  - module: docmirror.middlewares
    replacement: docmirror.framework.middlewares
  - module: docmirror.exporters
    replacement: docmirror.output.exporters
  - module: docmirror.integration
    replacement: docmirror.sdk.integration
  - module: docmirror.di
    replacement: docmirror.framework.di

quarantine_modules:
  - module: docmirror.structure.ocr.recognize.runner_legacy
    owner: mirror-core
    reason: Active fallback OCR runner used by scanned pipeline.
    exit_criteria: "All scanned OCR call sites use the replacement OCR runner."
    review_by: "2026-08-01"
```

### 4.3 Why This Is The Root Fix

The manifest becomes the single source of truth for:

- import-linter contracts
- orphan module checks
- dynamic YAML module checks
- old-path compatibility tests
- docs old-path scans
- CI path filter validation
- deletion review
- package public API review

No checker should carry its own independent architecture model.

---

## 5. Enforcement Design

### 5.1 Import Reference Extraction

Upgrade graph scanning to include:

1. Python `import` and `from import`.
2. `importlib.import_module("...")`.
3. `__import__("...")`.
4. `unittest.mock.patch("...")`.
5. `pytest.monkeypatch.setattr("...")`.
6. YAML keys: `module`, `adapter`, `class`, `hook`, `path`.
7. JSON schema registry module references.
8. `pyproject.toml` script/entry-point references.
9. CI workflow path filters.
10. Markdown code/import references, classified as docs/history/current.

This makes patch strings first-class import contracts.

### 5.2 Checker Set

Add or upgrade:

```text
validate_clean_manifest.py
validate_removed_imports.py
validate_compatibility_imports.py
validate_orphan_modules.py
validate_allowlist_paths.py
validate_docs_architecture_refs.py
validate_ci_path_filters.py
validate_workflow_yaml.py
```

### 5.3 CI Profiles

```text
PR fast:
  compileall
  smoke imports
  clean manifest validation
  removed import scan
  workflow YAML parse

Nightly:
  full orphan scan
  vulture
  dependency graph report
  quarantine expiry report
```

### 5.4 Quality Gate Output

Every checker should output machine-readable JSON:

```json
{
  "checker": "orphan_modules",
  "status": "fail",
  "findings": [
    {
      "module": "docmirror.output.exporters.sql_orm",
      "role": "internal",
      "reason": "zero inbound refs and not in manifest",
      "action": "delete_or_mark_dynamic"
    }
  ]
}
```

This avoids burying architecture regressions in free-text logs.

---

## 6. Module Disposition Process

Every suspicious module gets one of five outcomes:

| Outcome | Meaning | Required action |
|---|---|---|
| Keep active | It is used by static/dynamic/public path | Add or verify manifest role |
| Wire | It is intended but not connected | Add call site/config entry/test |
| Move out | It is experimental/dev-only | Move to `examples/`, `scripts/`, or docs |
| Quarantine | It is transitional | Add owner, expiry, exit criteria |
| Delete | It has no valid role | Remove file and references |

Do not leave a module in "maybe future" state inside `docmirror/`.

### 6.1 Review Order For Current Candidates

P0: paths causing test or CI failures

```text
docmirror.plugins.runner patch strings
docmirror.plugins.licensing patch strings
docmirror.plugins.post_extract allowlist entries
docmirror.exporters allowlist entry
adaptive-routing workflow old core paths
docmirror/__init__.py old package map
```

P1: likely dead/orphan modules

```text
docmirror.eval.structure_diff
docmirror.eval.structure_gate_metrics
docmirror.evidence.source_resolver
docmirror.input.extraction.html_utils
docmirror.models.mirror.typed_span
docmirror.models.serialization
docmirror.output.exporters.document_flow
docmirror.output.exporters.mathml
docmirror.output.exporters.pdfua_validation
docmirror.output.exporters.sql_orm
docmirror.plugins._base.header_normalizer
docmirror.runtime.checkpoint_writer
docmirror.structure.tables.grid_tensor
docmirror.structure.tables.page_state
docmirror.structure.ocr.formula_evidence
```

P2: active legacy-named modules

```text
docmirror.models.mirror.legacy_project
docmirror.models.mirror.legacy_access
docmirror.structure.ocr.recognize.runner_legacy
docmirror.structure.ocr.preprocess.legacy_fallback
docmirror.structure.ocr.reconstruct.grid_legacy
```

P2 modules should be renamed only as part of a replacement plan, not in the cleanup pass.

---

## 7. Implementation Roadmap

### Phase 1: Stop The Bleeding — 已完成

Target: one day.

1. Update `docmirror/__init__.py` package docstring to canonical layers.
2. Update all test patch strings from old plugin paths to `_runtime` paths, unless choosing alias compatibility.
3. Fix `scripts/code_hygiene/allowlist.yaml` stale paths.
4. Fix `.github/workflows/adaptive-routing-regression.yml` path filters and YAML indentation.
5. Add a regression test:

```text
tests/contract/test_removed_import_paths.py
```

Assertions:

```python
removed = [
    "docmirror.core",
    "docmirror.adapters",
    "docmirror.middlewares",
    "docmirror.exporters",
    "docmirror.integration",
    "docmirror.deployment",
    "docmirror.di",
]
for module in removed:
    assert importlib.util.find_spec(module) is None
```

If plugin compatibility is retained, assert old plugin paths import and warn. If not retained, assert they are removed too.

### Phase 2: Introduce The Manifest — 已完成基础版

Target: two to three days.

1. Add `docmirror/configs/architecture/clean_manifest.yaml`.
2. Add typed loader:

```text
scripts/code_hygiene/clean_manifest.py
```

3. Update orphan checker to consume manifest roles.
4. Update allowlist validator to reject non-importable stale modules.
5. Add patch-string extraction to import graph.

### Phase 3: Classify Orphan Modules — 已完成

Target: one week, incremental commits.

For every orphan candidate:

1. Read module.
2. Search static refs, string refs, config refs, docs refs.
3. Run focused tests.
4. Choose disposition: keep/wire/move/quarantine/delete.
5. Add or update manifest entry.
6. Remove allowlist entries that merely hide uncertainty.

### Phase 4: Delete With Proof — 已完成

Target: after Phase 3.

For deletion PRs:

1. Show checker output proving no refs.
2. Remove file and docs/config references.
3. Run:

```text
python3 -m compileall -q docmirror
python3 -m pytest tests/smoke/test_imports.py -q
python3 -m pytest tests/unit/test_code_hygiene.py -q
python3 scripts/validate/validate_clean_manifest.py
```

4. Include "why safe" notes in commit message.

### Phase 5: Prevent Recurrence — 已完成基础版

Target: ongoing.

1. Add clean gate to PR CI.
2. Add nightly orphan/quarantine expiry report.
3. Require every new top-level package or dynamic module to be declared in manifest.
4. Require every compatibility path to have `remove_after`.
5. Fail CI if docs mention removed paths outside approved design-history folders.

---

## 8. Non-Regression Principles

Cleanup must not degrade these scenarios:

| Scenario | Protection |
|---|---|
| Public API `from docmirror import perceive_document` | smoke import + API contract tests |
| CLI parse/classify/plugins/benchmark/MCP/PDFUA | CLI import tests |
| Server/FastAPI outputs | server contract tests |
| Plugin community extraction | plugin runner tests |
| Premium/finance licensing | licensing tests with canonical patch paths |
| YAML-driven post-extract hooks | config dynamic import validator |
| UDTR/mirror output | vNext mirror tests |
| OCR/scanned fallback | active legacy-named module manifest entries |
| SDK packages | SDK package tests/build checks |
| Docs/CI path filters | workflow and docs validators |

Do not delete code just because it is not statically imported. Dynamic entry points must be modeled first.

---

## 9. Specific Design Decisions

### 9.1 Plugin Runtime Publicness

Decision to make:

```text
Is docmirror.plugins._runtime intentionally public?
```

Recommended answer:

```text
No. It is internal but testable.
```

Then expose stable public plugin APIs through:

```text
docmirror.plugins
docmirror.plugins.DomainPlugin
docmirror.plugins.PluginRegistry
docmirror.plugins.registry
docmirror.plugins.plugin_manager
docmirror.plugins.license_manager
```

Tests that patch internals may use `_runtime`, but docs should not advertise `_runtime` to users.

### 9.2 Exporter Publicness

`docmirror.output.exporters.*` should be internal implementation modules unless the project explicitly exposes exporter classes/functions.

Recommended:

- Public users call projection/output APIs, not individual exporter modules.
- Keep `output.exporters` modules only if reachable through dispatcher/config.
- Delete or move unused exporters after manifest classification.

### 9.3 Legacy-Named Active Modules

Do not rename in bulk. Rename only when replacing the underlying role.

Example:

```text
runner_legacy.py -> runner.py
```

is only valid when:

- all call sites are migrated,
- tests prove behavior parity,
- old name is either removed or compat-aliased with expiry,
- manifest marks the transition.

### 9.4 Experimental AI/Parser Backends

AI/parser backends can appear orphaned because they are selected by registry/config.

Best design:

- Every backend implements a protocol.
- Every backend is registered in a registry.
- Registry discovery is tested.
- Manifest marks backend modules as `registry_loaded`.

No backend should sit in `docmirror/input/adapters/ai/backends/` without registry evidence.

---

## 10. Definition Of Done

The cleanup is complete when:

1. No source/test/script references old removed paths except approved design-history docs.
2. All compatibility modules are declared, tested, warned, and have removal version.
3. All orphan modules are either:
   - statically referenced,
   - manifest dynamic,
   - manifest public,
   - manifest quarantined with expiry,
   - or deleted.
4. `scripts/code_hygiene/allowlist.yaml` contains no stale non-importable module paths.
5. All GitHub workflows parse and path filters point to existing canonical paths.
6. `docmirror/__init__.py` describes the current package layout.
7. CI runs a clean architecture gate on every PR.
8. Nightly produces a quarantine expiry report. [已完成]

---

## 11. Immediate Patch Plan — 已完成

Recommended first implementation batch:

```text
1. Update docmirror/__init__.py docstring.
2. Update plugin patch strings to docmirror.plugins._runtime.*.
3. Update licensing_exec patch strings.
4. Update code_hygiene allowlist old paths.
5. Fix adaptive-routing workflow paths and indentation.
6. Add removed-path scan test.
7. Add patch-string extraction to hygiene graph.
8. Re-run plugin/licensing/hygiene tests.
```

Recommended validation:

```text
python3 -m compileall -q docmirror
python3 -m pytest tests/smoke/test_imports.py -q
python3 -m pytest tests/unit/test_plugin_runner.py -q
python3 -m pytest tests/unit/test_cli_license_show.py -q
python3 -m pytest tests/unit/test_code_hygiene.py -q
```

Only after this should deletion work begin.

---

## 12. Final Principle

The cleanest codebase is not the one with the fewest files. It is the one where every file has a declared reason to exist, every public path is intentional, every dynamic path is visible to tooling, every compatibility promise expires, and every deletion is proven rather than guessed.
