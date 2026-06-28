# DocMirror 1.1 Structure Domain Decomposition Plan

**Date:** 2026-06-28  
**Status:** Design for implementation after OSS 1.0.0 release  
**Source:** `docmirror/` tree audit, architecture hotspot report, clean manifest, OSS 1.0 release readiness work  
**Scope:** `docmirror/structure/`, adjacent evidence/topology/table/OCR/layout modules, compatibility shims, import boundaries, validation gates  
**Goal:** Decompose the current `structure/` super-domain into stable domain packages without breaking OSS 1.0 public APIs, CLI behavior, package import purity, or existing parser scenarios.

---

## 0. Executive Conclusion

The current `docmirror/` tree is not broken because it is deep. The maximum file depth is 6, and that deepest path is configuration:

```text
docmirror/configs/yaml/test/gates/classify/_template.yaml
```

That depth is acceptable.

The actual architecture issue is that `docmirror/structure/` is too broad:

```text
structure = layout + OCR + tables + evidence plane + topology + geometry + verification + profile + scene + normalization
```

This makes `structure/` a super-domain. It is understandable to the original authors, but harder for new contributors because unrelated concepts live under the same root. It also makes import governance harder: a change to table reconstruction can accidentally pull OCR, evidence, or topology internals.

The correct 1.1 solution is not a blind directory flattening. The correct solution is a domain decomposition:

```text
docmirror/layout/
docmirror/ocr/
docmirror/tables/
docmirror/topology/
docmirror/geometry/
docmirror/evidence/   # extend existing package, do not create a duplicate one
```

The migration must be bridge-first:

1. Create new domain packages and compatibility shims.
2. Move low-risk modules first.
3. Keep old `docmirror.structure.*` imports working for at least one minor version.
4. Add machine gates so new code imports the new packages.
5. Remove old shims only after downstream compatibility has been proven.

The only safe principle is:

```text
Move ownership first, move files second, remove old paths last.
```

---

## 1. First-Principles Model

### 1.1 What A Package Boundary Means

A package boundary is not a folder preference. It is a promise about responsibility.

For DocMirror, the responsibility boundaries should follow the document processing chain:

```text
Input acceptance
  -> layout understanding
  -> OCR/scanned recovery
  -> table reconstruction
  -> evidence and trust
  -> topology and graph relations
  -> output serialization
```

Today, several of those responsibilities are mixed under `structure/`.

The desired 1.1 architecture should let a contributor answer these questions immediately:

| Question | Target package |
|---|---|
| How is a page segmented into zones? | `docmirror.layout` |
| How are scanned images converted to OCR tokens? | `docmirror.ocr` |
| How are tables detected, reconstructed, and composed? | `docmirror.tables` |
| Why is a field trusted? | `docmirror.evidence` |
| How do pages, regions, and blocks relate? | `docmirror.topology` |
| How are coordinates transformed, cropped, or verified? | `docmirror.geometry` |

### 1.2 What Must Not Change

This design must not disturb the OSS 1.0 release contract:

```text
import docmirror
docmirror --help
docmirror --version
docmirror doctor
docmirror parse ...
```

The following invariants must remain true:

1. `import docmirror` remains fast, silent, and dependency-light.
2. `docmirror --help` does not initialize OCR, license, server, AI, or plugin-heavy paths.
3. Public README commands keep working.
4. Optional dependencies stay behind feature execution paths.
5. Existing downstream imports from `docmirror.structure.*` continue to work during the migration window.
6. Release gates and clean gates stay green after every phase.

### 1.3 What The Design Optimizes For

The goal is not minimal file count. The goal is:

```text
maximum conceptual clarity
minimum compatibility breakage
machine-enforced boundaries
small reversible migration steps
```

That means some compatibility modules will temporarily look redundant. That is acceptable if they protect users and keep the release stable.

---

## 2. Current State

### 2.1 Tree Audit Summary

Current `docmirror/` summary:

```text
directories: 126
files:       650
max depth:   6
```

Top-level implementation concentration:

| Package | Directories | Files | Max file depth |
|---|---:|---:|---:|
| `structure/` | 34 | 208 | 5 |
| `configs/` | 22 | 98 | 6 |
| `plugins/` | 14 | 82 | 5 |
| `input/` | 18 | 59 | 5 |
| `models/` | 5 | 48 | 3 |
| `framework/` | 8 | 34 | 4 |

`configs/` is deepest, but it is not the primary design risk. It is structured configuration.

`structure/` is the main architectural risk because it contains many different domains.

### 2.2 Hotspot Report Snapshot

Current hotspot report after OSS 1.0 cleanup:

```text
large_files=2
large_functions=6
optional_import_warnings=0
```

Largest structure-related files:

```text
docmirror/structure/evidence_plane.py
docmirror/structure/page_topology.py
docmirror/structure/ocr/formula_ast.py
docmirror/models/entities/parse_result.py
```

Largest functions include:

```text
docmirror/structure/tables/engine.py::extract_tables_layered
docmirror/structure/ocr/scanned/analyze_page.py::analyze_scanned_page
docmirror/structure/tables/engine.py::_extract_tables_layered_registry
docmirror/structure/ocr/recognize/runner_legacy.py::_run_ocr
```

This confirms the problem:

```text
The architecture debt is concentrated in domain-heavy implementation modules,
not in root-level project hygiene.
```

### 2.3 Existing Clean Gates

The existing clean manifest already protects broad layers:

```text
input     must not import server/cli/sdk
structure must not import server/cli/sdk/plugins
output    must not import server/cli/sdk
plugins   must not import selected core internals
models    must not import input/structure/output/server/cli/plugins, except allowlisted shims
```

This is valuable, but it is too coarse for the next stage. Once `structure/` is decomposed, the gate must become domain-aware:

```text
layout must not import OCR
OCR must not import tables as orchestration
tables must not import plugins/server/cli
evidence must not import server/cli
topology must not import OCR engines
geometry must be dependency-light
```

---

## 3. Root Cause Analysis

### 3.1 The Current `structure/` Package Has Multiple Meanings

`structure/` currently means all of these:

```text
document physical structure
page topology
OCR reconstruction
scanned document recovery
table reconstruction
layout segmentation
geometry and verification
evidence plane
scene/profile analysis
```

That is too much semantic load for one package.

### 3.2 Why This Hurts Contributors

A contributor looking for table logic sees:

```text
structure/tables/
structure/fusion.py
structure/ocr/page_canvas/
structure/evidence_plane.py
models/entities/parse_result.py
```

The mental map is not obvious.

A contributor looking for OCR sees:

```text
structure/ocr/
input/extraction/extractor.py
structure/segment/
models/mirror/page_canvas_export.py
```

The execution path crosses many domains.

### 3.3 Why This Hurts Import Boundaries

The OSS 1.0 cleanup already fixed public import purity by using lazy exports. But the current structure still makes accidental eager imports easy.

Example class of problem:

```text
import docmirror.structure.segment.negative_space
  -> parent package imports broader structure exports
  -> structure exports import evidence/topology/OCR
  -> OCR imports optional numpy/cv2/RapidOCR
```

This specific problem has been fixed, but the root risk remains unless package domains become explicit.

---

## 4. Target Domain Architecture

### 4.1 Target Package Map

Target 1.1 package shape:

```text
docmirror/
  layout/
    segment/
    profile/
    scene/
    normalization/

  ocr/
    backends/
    preprocess/
    recognize/
    scanned/
    page_canvas/
    local_structure/
    vision/
    field_grid/
    micro_grid/

  tables/
    access/
    char/
    compose/
    layers/
    pipeline/
    statement/
    structure_detect/
    fusion.py

  evidence/
    plane.py
    ledger.py
    source_span.py
    visual.py
    visual_graph.py
    quality.py
    quality_decision.py
    diff_engine.py
    overlay_manifest.py

  topology/
    page.py
    region_graph/
    relations/
    resolution/

  geometry/
    bbox.py
    transforms.py
    verification/
```

### 4.2 Current-To-Target Mapping

| Current path | Target path | Notes |
|---|---|---|
| `structure/segment/` | `layout/segment/` | Page zoning and segmentation. |
| `structure/profile/` | `layout/profile/` | Layout profile selection. |
| `structure/scene/` | `layout/scene/` | Scene detection. |
| `structure/normalization/` | `layout/normalization/` | Deskew/normalization; keep optional deps lazy. |
| `structure/ocr/` | `ocr/` | Scanned recovery and OCR internals. |
| `structure/tables/` | `tables/` | Table extraction and composition. |
| `structure/fusion.py` | `tables/fusion.py` | Table result fusion. |
| `structure/evidence_plane.py` | `evidence/plane.py` | Merge into existing evidence package. |
| `structure/page_topology.py` | `topology/page.py` | Page/document topology. |
| `structure/region_graph/` | `topology/region_graph/` | Region graph. |
| `structure/relations/` | `topology/relations/` | Relation model. |
| `structure/resolution/` | `topology/resolution/` | Resolution and reconciliation. |
| `structure/geometry/` | `geometry/` | Geometry primitives. |
| `structure/verification/` | `geometry/verification/` | Crop/coordinate verification. |
| `structure/analysis/` | split between `layout/analysis/` and `topology/analysis/` | Decide per module. |
| `structure/utils/` | avoid direct package move; split by owner | Vocabulary to tables/layout as needed. |
| `structure/structure/` | rename or dissolve | Name is ambiguous and should not survive 1.1. |

### 4.3 Domain Responsibilities

#### `layout`

Owns:

```text
zones
layout analysis
layout profiles
scene classification
normalization required before layout analysis
```

Does not own:

```text
OCR engine execution
table logical composition
evidence ledger
plugin domain extraction
server output
```

Allowed dependencies:

```text
models
runtime
configs
geometry
```

Forbidden dependencies:

```text
ocr engine internals
tables pipeline internals
plugins
server
cli
```

#### `ocr`

Owns:

```text
OCR preprocess
OCR recognition
scanned page recovery
page canvas
local structure recovery
vision OCR providers
formula OCR
```

Does not own:

```text
business document extraction
plugin-specific interpretation
final output serialization
```

Allowed dependencies:

```text
models
runtime
configs
geometry
layout contracts
```

Optional dependencies:

```text
numpy
cv2
rapidocr_onnxruntime
onnxruntime
rapid_latex_ocr
```

All optional dependencies must remain behind execution paths.

#### `tables`

Owns:

```text
table detection
character grid reconstruction
ledger/table postprocess
logical table composition
table quality
table access helpers
```

Does not own:

```text
OCR engine loading
plugin-specific final extraction
server responses
```

Allowed dependencies:

```text
models
runtime
configs
layout contracts
ocr token contracts
geometry
```

Forbidden dependencies:

```text
plugins
server
cli
```

#### `evidence`

Owns:

```text
evidence plane
source span ledger
visual evidence graph
quality decision
diff/canonicalization
redaction for evidence artifacts
```

Does not own:

```text
OCR recognition
table extraction algorithm
server transport
```

Important design choice:

```text
Use existing docmirror/evidence as the target.
Do not create a second evidence package.
```

#### `topology`

Owns:

```text
page topology
document topology
region graph
relationships
resolution/reconciliation between page entities
```

Does not own:

```text
OCR engines
table algorithms
server/API concerns
```

#### `geometry`

Owns:

```text
bbox math
coordinate transforms
page/image coordinate conversion
verification crops
geometric primitives
```

Does not own:

```text
domain semantics
OCR recognition
table reconstruction policy
```

Geometry should be the most dependency-light domain.

---

## 5. Target Dependency Graph

The target graph should be mostly acyclic:

```text
configs/runtime/models
        |
        v
geometry
        |
        v
layout --------+
        |      |
        v      v
ocr       tables
        \      /
         v    v
        evidence
           |
           v
        topology
           |
           v
        output/server/cli
```

More precisely:

```text
geometry -> models/runtime/configs only
layout   -> geometry/models/runtime/configs
ocr      -> geometry/layout contracts/models/runtime/configs
tables   -> geometry/layout contracts/ocr token contracts/models/runtime/configs
evidence -> geometry/layout/ocr/tables/topology contracts/models/runtime/configs
topology -> geometry/evidence contracts/models/runtime/configs
output   -> evidence/topology/models/runtime/configs
server   -> output/models/runtime/configs
cli      -> public commands and lazy feature entry points
plugins  -> public contracts, not internal algorithms
```

The exact graph can be loosened during transition, but the direction must not reverse for new code.

---

## 6. Compatibility Strategy

### 6.1 Compatibility Shims

Existing imports must keep working during 1.1:

```python
from docmirror.structure.ocr.recognize.runner_legacy import _run_ocr
from docmirror.structure.tables.engine import extract_tables_layered
from docmirror.structure.segment.zones import Zone
```

After moving files, old paths should become shims:

```python
# docmirror/structure/tables/engine.py
from docmirror.tables.engine import *  # noqa: F403
```

Use shims only for compatibility, not for new code.

### 6.2 Shim Rules

1. Shims must contain no business logic.
2. Shims must be dependency-light.
3. Shims must not import optional dependencies at module import time.
4. Shims must include a removal target comment:

```python
# Compatibility shim. New imports should use docmirror.tables.engine.
# Remove after: 1.2 or next major compatibility window.
```

5. Shims must be listed in a migration manifest:

```text
docmirror/configs/architecture/domain_decomposition.yaml
```

### 6.3 Deprecation Policy

Recommended policy:

```text
1.1.0: new paths available; old paths work silently.
1.1.x: internal code migrated to new paths; warnings optional for direct user imports.
1.2.0: old paths still work, but release notes announce removal window.
2.0.0 or later: remove old shims if ecosystem impact is acceptable.
```

Do not emit noisy deprecation warnings from common import paths in 1.1.0. Warnings can break tests and annoy users. Prefer documentation and lint gates first.

---

## 7. Migration Phases

### Phase 0: Freeze Domain Manifest

Status: not started.

Goal:

```text
Make the desired domain decomposition machine-readable before moving files.
```

Tasks:

1. Add:

```text
docmirror/configs/architecture/domain_decomposition.yaml
```

2. Define target domains:

```yaml
domains:
  layout:
    target_path: docmirror/layout
    old_paths:
      - docmirror/structure/segment
      - docmirror/structure/profile
      - docmirror/structure/scene
      - docmirror/structure/normalization
  ocr:
    target_path: docmirror/ocr
    old_paths:
      - docmirror/structure/ocr
  tables:
    target_path: docmirror/tables
    old_paths:
      - docmirror/structure/tables
      - docmirror/structure/fusion.py
  evidence:
    target_path: docmirror/evidence
    old_paths:
      - docmirror/structure/evidence_plane.py
  topology:
    target_path: docmirror/topology
    old_paths:
      - docmirror/structure/page_topology.py
      - docmirror/structure/region_graph
      - docmirror/structure/relations
      - docmirror/structure/resolution
  geometry:
    target_path: docmirror/geometry
    old_paths:
      - docmirror/structure/geometry
      - docmirror/structure/verification
```

3. Add validator:

```text
scripts/validate/validate_domain_decomposition.py
```

Validation:

```bash
python scripts/validate/validate_domain_decomposition.py
make validate-clean
```

Exit criteria:

```text
The future domain map exists and is validated before any move.
```

### Phase 1: Create Target Packages With No Logic Moves

Status: not started.

Goal:

```text
Create stable target package entry points without changing behavior.
```

Tasks:

1. Add empty/lazy package roots:

```text
docmirror/layout/__init__.py
docmirror/ocr/__init__.py
docmirror/tables/__init__.py
docmirror/topology/__init__.py
docmirror/geometry/__init__.py
```

2. Export only public contracts from each package.
3. Do not move implementation files yet.
4. Add tests that importing these packages is silent and optional-dependency-light.

Validation:

```bash
python scripts/validate/validate_import_purity.py
pytest tests/contract/test_minimal_import_contract.py -q
```

Exit criteria:

```text
New target packages can be imported without triggering heavy dependencies.
```

### Phase 2: Low-Risk Layout And Geometry Move

Status: not started.

Goal:

```text
Move the least risky, most independent domains first.
```

Move:

```text
structure/geometry/      -> geometry/
structure/verification/  -> geometry/verification/
structure/profile/       -> layout/profile/
structure/scene/         -> layout/scene/
structure/normalization/ -> layout/normalization/
structure/segment/       -> layout/segment/
```

Rules:

1. Use `git mv`.
2. Leave old-path shims.
3. Update internal imports to new paths in touched modules.
4. Do not migrate unrelated code in the same patch.

Validation:

```bash
make validate-release
make validate-clean
pytest tests/contract tests/smoke -q
```

Exit criteria:

```text
Layout and geometry have new ownership. Old imports still work.
```

### Phase 3: Tables Domain Move

Status: not started.

Goal:

```text
Give table extraction and composition an explicit top-level domain.
```

Move:

```text
structure/tables/ -> tables/
structure/fusion.py -> tables/fusion.py
```

Hotspots to preserve carefully:

```text
structure/tables/engine.py::extract_tables_layered
structure/tables/engine.py::_extract_tables_layered_registry
```

Tasks:

1. Move files with compatibility shims.
2. Update imports in `input/extraction`, `models/mirror`, and table tests.
3. Add import-linter rule:

```text
tables must not import plugins/server/cli
```

4. Add contract test:

```text
import docmirror.tables
```

must not load OCR engine modules.

Validation:

```bash
pytest tests/unit tests/contract tests/smoke -q
make validate-clean
```

Exit criteria:

```text
Tables become a first-class domain with no server/plugin coupling.
```

### Phase 4: OCR Domain Move

Status: not started.

Goal:

```text
Move OCR and scanned recovery into a domain that is clearly optional-dependency guarded.
```

Move:

```text
structure/ocr/ -> ocr/
```

Critical subdomains:

```text
backends
preprocess
recognize
scanned
page_canvas
local_structure
vision
field_grid
micro_grid
```

Rules:

1. Every optional dependency must use `require_optional_module(s)`.
2. `import docmirror.ocr` must not load `numpy`, `cv2`, `onnxruntime`, or `rapidocr_onnxruntime`.
3. Feature execution may load optional dependencies.
4. Legacy modules `runner_legacy`, `legacy_fallback`, and `grid_legacy` remain quarantined until replacements are ready.

Validation:

```bash
python scripts/validate/validate_import_purity.py
python scripts/validate/report_architecture_hotspots.py --fail-optional-leaks
make smoke-extras
pytest tests/contract tests/smoke -q
```

Exit criteria:

```text
OCR is a top-level optional domain with no import-time optional dependency leaks.
```

### Phase 5: Evidence Plane Merge

Status: not started.

Goal:

```text
Unify trust/evidence concepts under the existing evidence package.
```

Move:

```text
structure/evidence_plane.py -> evidence/plane.py
```

Current related package:

```text
docmirror/evidence/
```

Tasks:

1. Move `EvidencePlane`, `EvidencePage`, `DocumentSource`, and `EvidencePlaneBuilder`.
2. Make `docmirror.evidence` the canonical public domain for evidence.
3. Update `models.mirror` allowlist paths.
4. Leave `structure/evidence_plane.py` shim.
5. Add schema/contract tests for evidence output shape.

Validation:

```bash
pytest tests/contract tests/unit/test_*evidence* -q
make validate-clean
```

Exit criteria:

```text
There is one evidence domain, not two parallel evidence concepts.
```

### Phase 6: Topology Domain Move

Status: not started.

Goal:

```text
Separate document/page graph relationships from extraction algorithms.
```

Move:

```text
structure/page_topology.py -> topology/page.py
structure/region_graph/ -> topology/region_graph/
structure/relations/ -> topology/relations/
structure/resolution/ -> topology/resolution/
```

Tasks:

1. Move topology files.
2. Update evidence/output references to topology contracts.
3. Add import-linter rule:

```text
topology must not import OCR engines or table extraction engines
```

Validation:

```bash
pytest tests/contract tests/smoke -q
make validate-clean
```

Exit criteria:

```text
Topology is a graph/relationship domain, not a mixed extraction domain.
```

### Phase 7: Clean Up `structure/`

Status: not started.

Goal:

```text
Reduce `structure/` to compatibility-only or remove it after migration window.
```

Tasks:

1. Audit all remaining `docmirror.structure.*` imports.
2. Convert internal imports to new canonical domains.
3. Keep only compatibility shims in `structure/`.
4. Update docs and examples.
5. Add gate that new source files cannot import old `structure` paths except shims/tests.

Validation:

```bash
rg "from docmirror\\.structure|import docmirror\\.structure" docmirror tests scripts
python scripts/validate/validate_domain_decomposition.py --strict-new-imports
```

Exit criteria:

```text
Internal code uses canonical domains; `structure/` is compatibility-only.
```

---

## 8. Machine Gates

### 8.1 Domain Decomposition Validator

Add:

```text
scripts/validate/validate_domain_decomposition.py
```

Responsibilities:

1. Validate target packages exist.
2. Validate compatibility shims exist for moved paths.
3. Validate old paths do not contain business logic after migration.
4. Validate new code does not import old `docmirror.structure.*` paths.
5. Validate optional dependencies are not imported at package import time.
6. Validate all moved modules are listed in the manifest.

Suggested command:

```bash
python scripts/validate/validate_domain_decomposition.py
```

### 8.2 Import-Linter Contracts

Extend clean manifest with domain contracts:

```yaml
layers:
  layout:
    paths:
      - docmirror/layout/**
    forbidden_imports:
      - docmirror.ocr.vision
      - docmirror.server
      - docmirror.cli
      - docmirror.plugins

  ocr:
    paths:
      - docmirror/ocr/**
    forbidden_imports:
      - docmirror.server
      - docmirror.cli
      - docmirror.plugins

  tables:
    paths:
      - docmirror/tables/**
    forbidden_imports:
      - docmirror.server
      - docmirror.cli
      - docmirror.plugins

  topology:
    paths:
      - docmirror/topology/**
    forbidden_imports:
      - docmirror.ocr.vision
      - docmirror.tables.engine
      - docmirror.server
      - docmirror.cli
```

### 8.3 Hotspot Gate Evolution

Current hotspot thresholds:

```text
file > 1500 lines: warn
function > 250 lines: warn
optional import warning: report
```

1.1 should keep historical warnings as report-only, but fail on new regressions:

```text
new file > 1500 lines: fail
new function > 250 lines: fail unless allowlisted
new top-level optional import leak: fail
```

This prevents new debt while avoiding destabilizing old modules during migration.

---

## 9. Public API And Compatibility Contract

The following public imports must continue to work:

```python
import docmirror
from docmirror import perceive_document
from docmirror.models import ParseResult
from docmirror.models.entities import ParseResult
```

The following legacy internal imports should continue during 1.1:

```python
from docmirror.structure.segment.zones import Zone
from docmirror.structure.ocr.page_canvas.models import PageCanvas
from docmirror.structure.tables.engine import extract_tables_layered
from docmirror.structure.evidence_plane import EvidencePlane
```

New canonical imports should become:

```python
from docmirror.layout.segment.zones import Zone
from docmirror.ocr.page_canvas.models import PageCanvas
from docmirror.tables.engine import extract_tables_layered
from docmirror.evidence.plane import EvidencePlane
```

Do not break old paths until the migration window closes.

---

## 10. Risk Matrix

| Risk | Impact | Mitigation |
|---|---|---|
| Internal import breakage | Tests fail, parse paths break | Move in small phases, keep shims, run contract/smoke gates after each phase. |
| Optional dependency regression | Minimal install breaks | Import purity validator and hotspot optional import gate. |
| Public API breakage | Downstream users fail | Keep `docmirror.__init__`, `docmirror.models`, and old structure shims lazy. |
| Circular imports | Runtime import errors | Define domain graph and use import-linter. |
| Documentation drift | Contributors use old paths | Update README/docs/examples per phase. |
| Too much refactor in one PR | Hard to review/revert | One domain per patch batch. |
| Shim sprawl | Old paths never die | Track shims in manifest with removal target. |

---

## 11. Recommended Patch Batches

### Batch 1: Manifest And Validator

Files:

```text
docmirror/configs/architecture/domain_decomposition.yaml
scripts/validate/validate_domain_decomposition.py
Makefile
```

Commands:

```bash
python scripts/validate/validate_domain_decomposition.py
make validate-clean
```

### Batch 2: Empty Target Packages

Files:

```text
docmirror/layout/__init__.py
docmirror/ocr/__init__.py
docmirror/tables/__init__.py
docmirror/topology/__init__.py
docmirror/geometry/__init__.py
tests/contract/test_domain_package_imports.py
```

Commands:

```bash
pytest tests/contract/test_domain_package_imports.py -q
python scripts/validate/validate_import_purity.py
```

### Batch 3: Layout And Geometry

Move:

```text
structure/segment -> layout/segment
structure/profile -> layout/profile
structure/scene -> layout/scene
structure/normalization -> layout/normalization
structure/geometry -> geometry
structure/verification -> geometry/verification
```

Commands:

```bash
make validate-release
make validate-clean
pytest tests/contract tests/smoke -q
```

### Batch 4: Tables

Move:

```text
structure/tables -> tables
structure/fusion.py -> tables/fusion.py
```

Commands:

```bash
pytest tests/unit tests/contract tests/smoke -q
make validate-clean
```

### Batch 5: OCR

Move:

```text
structure/ocr -> ocr
```

Commands:

```bash
python scripts/validate/report_architecture_hotspots.py --fail-optional-leaks
make smoke-extras
pytest tests/contract tests/smoke -q
```

### Batch 6: Evidence And Topology

Move:

```text
structure/evidence_plane.py -> evidence/plane.py
structure/page_topology.py -> topology/page.py
structure/region_graph -> topology/region_graph
structure/relations -> topology/relations
structure/resolution -> topology/resolution
```

Commands:

```bash
make validate-release
make validate-clean
pytest tests/contract tests/smoke -q
```

### Batch 7: Internal Import Migration

Tasks:

```text
Update internal imports to new canonical domains.
Keep old structure shims for external compatibility.
Add strict-new-imports mode to validator.
```

Commands:

```bash
python scripts/validate/validate_domain_decomposition.py --strict-new-imports
rg "docmirror\\.structure" docmirror tests scripts
```

---

## 12. Definition Of Done

The domain decomposition is complete when:

1. `docmirror/layout`, `docmirror/ocr`, `docmirror/tables`, `docmirror/evidence`, `docmirror/topology`, and `docmirror/geometry` exist as canonical domains.
2. Internal code imports canonical domains, not old `docmirror.structure.*` paths.
3. Old `docmirror.structure.*` paths remain available as compatibility shims during the migration window.
4. `import docmirror` remains fast, silent, and dependency-light.
5. `docmirror --help`, `docmirror doctor`, and README commands still work in base install.
6. `optional_import_warnings=0` remains true.
7. `make validate-release` passes.
8. `make validate-clean` passes.
9. Contract and smoke tests pass.
10. Public docs explain the canonical domain packages.
11. Shim manifest lists every old path and removal target.
12. No new large file/function hotspot is introduced without an explicit allowlist entry.

---

## 13. Non-Goals

This design does not require:

1. Rewriting parsing algorithms.
2. Changing public output schemas.
3. Removing old import paths immediately.
4. Changing plugin contracts.
5. Changing CLI behavior.
6. Changing package name or PyPI metadata.
7. Moving `configs/` only to reduce depth.

These are intentionally excluded to keep the migration safe.

---

## 14. Final Recommendation

Do not restructure `docmirror/` before OSS 1.0.0.

For 1.1, implement this decomposition in small batches. The highest-leverage first step is not moving files. It is adding a domain decomposition manifest and validator so every later move is governed.

The target state should make DocMirror feel obvious:

```text
layout   = where things are on the page
ocr      = what scanned pixels say
tables   = how grids become logical tables
evidence = why outputs are trustworthy
topology = how document parts relate
geometry = how coordinates are transformed and verified
```

That is the durable architecture. It is also the cleanest bridge between the current implementation and a contributor-friendly open-source 1.1.
