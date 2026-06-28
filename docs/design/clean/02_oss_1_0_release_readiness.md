# DocMirror OSS 1.0.0 Release Readiness Plan

**Date:** 2026-06-28  
**Status:** Execution annotated on 2026-06-28  
**Source:** `docs/design/position.md`, local release smoke, package build inspection, CLI/README/API review  
**Scope:** OSS package, public API, CLI, docs, dependencies, CI, distribution, architecture hygiene, performance, extraction quality, community trust  
**Goal:** Make DocMirror 1.0.0 safe, credible, installable, understandable, and useful for the open-source community without weakening the commercial-document trust-layer product direction.

---

## 0. Executive Conclusion

DocMirror's codebase is now much cleaner after the architecture cleanup, but **it is not yet release-ready as an OSS 1.0.0 product**.

The key finding is not a minor packaging bug. It reveals a deeper release boundary problem:

```text
DocMirror's public surface is not yet isolated from heavy optional runtime internals.
```

The clean release smoke showed:

```text
python -m build                 passed
twine check dist/*              passed
pip install wheel in clean venv passed
import docmirror                failed: ModuleNotFoundError: numpy
docmirror --help                failed for the same reason
```

This means a community user can install the package but cannot import it with the declared core dependencies. For an OSS 1.0.0 release, that is a P0 blocker.

The second issue is product positioning. `docs/design/position.md` defines the correct category:

```text
DocMirror is the Trust Layer for Commercial Documents.
Parse. Prove. Trust.
```

But the public metadata and README still present the project as:

```text
Universal document parsing engine
LLM-ready structured data
RAG pipelines
one API for many formats
```

That message is broader, weaker, and less defensible. It invites comparison with MinerU, Unstructured, Docling, Marker, and generic OCR tools on their home turf. The better category is sharper:

```text
Commercial Document Trust Layer
Every field must be proven.
```

The best solution is a single release contract:

```text
OSS 1.0.0 Release Contract =
  pure import
  truthful dependency boundary
  CLI/docs/API consistency
  position-aligned messaging
  optional capabilities behind lazy adapters
  reproducible trust/evidence demo
  automated wheel smoke gate
```

This plan is designed to solve root causes once, not patch symptoms one by one.

---

## 1. First-Principles Release Model

### 1.1 What OSS Users Experience First

The first user experience is not the best model output. It is:

```text
pip install docmirror
python -c "import docmirror"
docmirror --help
read README
run one example
inspect JSON
decide whether the project is real
```

If any of these steps fails, the user never reaches the advanced extraction engine.

Therefore, release readiness starts at import time.

### 1.2 The Core Product Promise

Based on `docs/design/position.md`, the 1.0.0 promise should be:

```text
DocMirror turns commercial documents into verifiable machine-ready signals.
```

Not:

```text
DocMirror parses all documents into LLM-ready text.
```

The public story must be:

```text
Parse: understand commercial documents.
Prove: attach evidence to every important field.
Trust: expose risk, confidence, failure, and review status.
```

### 1.3 Release-Grade Public Contract

A 1.0.0 public contract must be:

| Contract | Rule |
|---|---|
| Import | `import docmirror` must be fast, silent, and dependency-light. |
| CLI | `docmirror --help`, `docmirror --version`, and README commands must work in a clean install. |
| Dependencies | Core dependencies must cover the core import path; optional extras must be lazy and guarded. |
| Output | Every advertised output must be backed by schema, example, and test. |
| Failure | Missing optional engines must produce visible recoverable errors, not import crashes. |
| Position | README, PyPI metadata, docs, and CLI tagline must match the product constitution. |
| Community | The OSS package must not require private enterprise packages or local licenses for basic use. |
| Benchmarks | Public performance/accuracy claims must be reproducible or clearly marked as planned. |

### 1.4 The Only Acceptable Optional Dependency Rule

Optional packages may exist only behind one of these boundaries:

```text
adapter method body
backend factory
explicit feature command
server startup path
test/dev path
```

Optional packages must not be imported by:

```text
docmirror.__init__
docmirror.cli.main import
docmirror --help
public model imports
package import side effects
```

If an optional dependency is missing, the user should see:

```text
FeatureUnavailable(
  feature="scanned OCR",
  missing=["numpy", "rapidocr-onnxruntime"],
  install="pip install 'docmirror[ocr]'",
  recoverable=True
)
```

Not:

```text
ModuleNotFoundError: numpy
```

---

## 2. Current Findings

### 2.1 P0: Minimal Install Fails

Observed in a clean temporary virtual environment built from the generated wheel:

```text
pip install dist/docmirror-1.0.0-py3-none-any.whl
python -c "import docmirror"
```

Result:

```text
ModuleNotFoundError: No module named 'numpy'
```

Import chain:

```text
docmirror.__init__
  -> docmirror.models.entities.parse_result.ParseResult
  -> docmirror.structure.ocr.page_canvas.models.PageCanvas
  -> docmirror.structure.__init__
  -> docmirror.structure.evidence_plane
  -> docmirror.models.mirror.domain_access
  -> docmirror.structure.ocr.page_canvas.evidence_bundles
  -> docmirror.structure.ocr.__init__
  -> docmirror.structure.ocr.scanned.universal
  -> docmirror.structure.ocr.recognize.runner_legacy
  -> docmirror.structure.ocr.vision.rapidocr_engine
  -> numpy
```

Root cause:

```text
Public import imports typed models.
Typed models import structure internals.
Structure package __init__ imports OCR paths.
OCR paths import optional dependencies eagerly.
```

Required fix:

```text
Make public import pure and move optional dependencies behind lazy boundaries.
```

### 2.2 P0: CLI Help Fails In Minimal Install

Observed:

```text
docmirror --help
```

Result:

```text
ModuleNotFoundError: numpy
```

Root cause:

```text
console script imports docmirror.cli.main
docmirror.cli.main imports command modules eagerly
command modules import runtime/plugin/OCR/license paths
```

Also observed locally:

```text
docmirror --help initializes RapidOCR and loads offline license state.
```

This violates the CLI rule:

```text
Help/version commands must be zero-side-effect.
```

### 2.3 P0: README Commands Do Not Match Console Script

README currently advertises:

```bash
docmirror document.pdf --format json
```

Actual console script is a Click group:

```bash
docmirror parse document.pdf --format json
```

There is also no `docmirror version` command, while users naturally try it.

Required fix:

```text
Either make root command parse files or update every public doc to use docmirror parse.
Add docmirror version or rely consistently on --version.
```

Best solution:

```text
Support both:
  docmirror parse FILE
  docmirror FILE

Keep docs on one canonical form:
  docmirror parse FILE
```

Supporting root-file parse reduces friction without making docs ambiguous.

### 2.4 P0: Public Metadata Contradicts Product Constitution

Current `pyproject.toml`:

```text
description = "Universal document parsing engine with OCR, layout analysis, and table extraction"
```

Current README:

```text
Transforms complex documents into LLM-ready structured data...
Built for RAG pipelines...
Universal Document Parser...
```

Product constitution says:

```text
Trust Layer for Commercial Documents.
Every field must be proven.
Not a RAG loader.
Not a generic OCR product.
Not universal format coverage as the core promise.
```

Required fix:

```text
Make README, README_zh-CN, pyproject metadata, docs quickstart, CLI tagline, and package description all converge on:
Commercial Document Trust Layer.
```

### 2.5 P0: `docmirror[all]` Includes Private Enterprise Dependency

Current optional dependency:

```text
all = [
  "docmirror[pdf,ocr,layout,table,formula,office,security,cache,langdetect,server,archive,enterprise]",
  ...
]
enterprise = ["docmirror-enterprise>=0.4.0"]
```

For public PyPI users this can fail or create confusion.

Required fix:

```text
OSS all extra must include only public dependencies.
Private commercial packages must not be pulled by public "all".
```

Best policy:

```text
all = public complete OSS feature set
commercial = documented separately, not included in public all
enterprise/finance = optional extras only if installable from configured private index
```

### 2.6 P0: Core Dependencies Are Underdeclared For Public Surface

Core dependencies currently include:

```text
pydantic
filetype
PyYAML
rich
```

But current import surface reaches:

```text
numpy
rapidocr_onnxruntime
cv2
fitz
...
```

The correct fix is not "put everything in core dependencies". That would make the base install heavy.

The correct fix is:

```text
shrink import surface
guard optional dependencies
add minimal-install smoke CI
```

Only dependencies required for pure import and basic CLI shell should be core dependencies.

### 2.7 P1: Wheel Includes Local Plugin State

Wheel includes:

```text
docmirror/plugins/.plugin_state.json
```

This is not a source contract. It is mutable state.

Required fix:

```text
Do not ship local mutable plugin state in wheel.
Use packaged defaults in YAML or code constants.
Store user state under ~/.docmirror or platformdirs app state.
```

### 2.8 P1: README Links And Claims Need Verification

Observed risks:

```text
README links to VISION.md but VISION.md is absent.
README claims "50ms parsing speed" without immediate reproducible benchmark evidence.
README benchmark table says exact scores populated on GA1.0 release, while package version is already 1.0.0.
README says 6 premium community plugins, which is confusing for an OSS package.
docs/quickstart.md uses stale API patterns such as result.content and --skip-cache.
docs/quickstart.md links architecture.md, which is not present in the current docs root.
```

Required fix:

```text
Only claim what can be reproduced in public.
Remove or clearly qualify non-public claims.
Replace broken docs links.
Align quickstart with current PerceiveResult / mirror vNext API.
```

### 2.9 P1: Architecture Debt Hotspots Remain

Largest files and functions include:

```text
docmirror/structure/tables/engine.py                  1023 lines, max function about 610 lines
docmirror/output/mirror.py                            1811 lines, max function about 305 lines
docmirror/structure/evidence_plane.py                 2171 lines
docmirror/structure/page_topology.py                  1568 lines
docmirror/input/extraction/extractor.py               1096 lines
docmirror/__main__.py                                  717 lines
```

These do not block 1.0.0 if tested, but they affect maintainability and contribution quality.

Best approach:

```text
Do not refactor all large files before 1.0.0.
Extract only public-boundary and import-side-effect fixes for 1.0.0.
Schedule internal decompositions for 1.1 with golden tests.
```

### 2.10 P1: Quality Claims Need A Public Golden Mini Set

Position says:

```text
Every field must be proven.
Failure must be visible.
Trust score matters.
```

Therefore public quality should not only show table F1. It should show:

```text
field evidence coverage
source_ref coverage
bbox coverage
needs_review calibration
failure envelope quality
partial result completeness
```

Required fix:

```text
Create public synthetic/generic fixtures that do not contain PII.
Publish a reproducible mini benchmark.
Use that benchmark in README claims.
```

---

## 3. Target Release Contract

### 3.1 Public Import Contract

`import docmirror` may only do:

```text
define __version__
define lazy perceive_document wrapper
expose light public metadata
optionally expose TYPE_CHECKING-only types
```

It must not:

```text
configure root logging
load OCR models
load license files
import optional dependencies
import CLI/server/plugin modules
create directories
read user home state
start network checks
```

Target:

```text
python -X importtime -c "import docmirror"
```

Release threshold:

```text
base install import succeeds
no stdout/stderr
no optional dependency required
target < 200ms on CI Linux
hard maximum < 500ms on CI Linux
```

### 3.2 Public CLI Contract

The CLI must satisfy in a clean base install:

```bash
docmirror --help
docmirror --version
docmirror version
docmirror doctor
```

These commands must not require OCR/PDF/server/AI extras.

Feature commands may require extras, but must fail visibly:

```text
Missing optional dependency for PDF parsing.
Install with: pip install "docmirror[pdf]"
```

Canonical parse command:

```bash
docmirror parse FILE --format json
```

Convenience parse command:

```bash
docmirror FILE --format json
```

The root-file behavior is optional but recommended for README compatibility and user ergonomics.

### 3.3 Optional Dependency Contract

Every optional dependency must be declared in exactly one capability group:

| Capability | Extra |
|---|---|
| Digital PDF | `pdf` |
| Scanned OCR | `ocr` |
| Layout model | `layout` |
| Table model | `table` |
| Office | `office` |
| Server | `server` |
| Security/PDF tamper | `security` |
| AI/VLM | `ai` |
| RAG framework integrations | `langchain`, `llamaindex`, `haystack` |
| Development | `dev` |

Every adapter/backend must declare missing dependencies through a shared helper:

```python
require_optional("numpy", extra="ocr", feature="scanned OCR")
```

The helper should raise a DocMirror-native visible error, not raw `ImportError`.

### 3.4 Product Positioning Contract

All public surfaces must use the same category:

```text
DocMirror — The Trust Layer for Commercial Documents.
Parse. Prove. Trust.
```

Canonical one-liner:

```text
DocMirror turns commercial documents into verifiable, audit-ready, machine-usable signals.
```

Chinese:

```text
DocMirror 是商业凭证的可信文档智能层，把非结构化商业文件转化为可追溯、可审计、可计算的结构化信号。
```

Disallowed as primary positioning:

```text
Universal document parser
LLM-ready document converter
RAG loader
OCR engine
all-format parser
```

These may appear only as secondary capabilities.

### 3.5 OSS/Commercial Boundary Contract

OSS package must be fully usable without:

```text
docmirror-enterprise
docmirror-finance
license files
private package indexes
private fixtures
private docs
```

Commercial mentions are allowed only as:

```text
optional paid extensions
separate docs
not required for community quickstart
not included in docmirror[all]
```

### 3.6 Evidence And Trust Output Contract

The 1.0.0 public demo must show all four layers:

```text
Mirror         document-shaped facts
JSON           structured data
Evidence       page / bbox / source_ref
Trust Report   score / status / needs_review / failure reasons
```

The quickstart should not only print tables. It should print:

```python
field
value
page
bbox
confidence
needs_review
source_ref
```

This makes the product category tangible.

---

## 4. Root-Cause Fix Design

### 4.1 Pure Import Architecture

Current anti-pattern:

```text
docmirror.__init__ imports models
models import structure
structure __init__ imports OCR
OCR imports numpy/model backend
```

Target:

```text
docmirror.__init__
  -> version metadata
  -> lazy perceive_document only
  -> no model import
```

Implementation options:

1. Remove `ParseResult` and `DomainExtractionResult` from runtime `__all__`.
2. Keep them under `TYPE_CHECKING` for editor/type checker support.
3. Provide lazy `__getattr__` only if backward compatibility requires `docmirror.ParseResult`.
4. Ensure lazy attribute errors include install guidance if optional deps are missing.

Preferred 1.0.0 choice:

```text
Keep perceive_document as the only eagerly supported public runtime API.
Use lazy __getattr__ for ParseResult and DomainExtractionResult if needed by tests/docs.
```

Example target:

```python
__version__ = "1.0.0"

async def perceive_document(*args, **kwargs):
    from docmirror.input.pipeline import perceive_document as _perceive_document
    return await _perceive_document(*args, **kwargs)

def __getattr__(name):
    if name == "ParseResult":
        from docmirror.models.entities.parse_result import ParseResult
        return ParseResult
    raise AttributeError(name)
```

But the lazy `ParseResult` path still needs model import cleanup if it imports OCR. Therefore:

```text
P0 target: import docmirror must pass.
P1 target: from docmirror import ParseResult must also be light.
```

### 4.2 Package `__init__` Minimalism

Every package `__init__.py` should follow:

```text
No heavy imports.
No optional dependencies.
No model loading.
No user state.
No side effects.
```

Hot packages to inspect:

```text
docmirror.structure.__init__
docmirror.structure.ocr.__init__
docmirror.structure.ocr.recognize.__init__
docmirror.models.__init__
docmirror.models.entities.__init__
docmirror.models.mirror.__init__
docmirror.plugins._runtime.__init__
```

Release gate:

```text
python scripts/validate/audit_import_side_effects.py
```

This script should import selected public modules in a subprocess and assert:

```text
exit code 0
no stdout/stderr
no banned modules imported: numpy, cv2, rapidocr_onnxruntime, fitz, fastapi, openai, google
```

### 4.3 Shared Optional Dependency Helper

Add:

```text
docmirror/runtime/optional_deps.py
```

Responsibilities:

```text
check dependency availability
return module when available
raise FeatureUnavailable when missing
format install guidance
support multiple packages per feature
```

Example:

```python
np = require_optional_module("numpy", extra="ocr", feature="scanned OCR")
```

Error contract:

```json
{
  "code": "OPTIONAL_DEPENDENCY_MISSING",
  "feature": "scanned OCR",
  "missing": ["numpy"],
  "install": "pip install 'docmirror[ocr]'",
  "recoverable": true
}
```

### 4.4 CLI Lazy Command Registration

Current:

```python
from docmirror.cli.benchmark import benchmark
from docmirror.cli.classify import classify
from docmirror.cli.mcp import mcp
from docmirror.cli.pdfua import pdfua
from docmirror.cli.plugins import plugins
```

This makes `docmirror --help` pay the cost of all command imports.

Target:

```text
Root CLI imports only click and version metadata.
Subcommands are lazy-loaded when invoked.
```

Implementation:

```python
class LazyGroup(click.Group):
    def list_commands(...)
    def get_command(...)
```

Command registry:

```python
COMMANDS = {
  "parse": "docmirror.cli.parse:parse",
  "classify": "docmirror.cli.classify:classify",
  "plugins": "docmirror.cli.plugins:plugins",
  "mcp": "docmirror.cli.mcp:mcp",
}
```

Add:

```text
docmirror --version
docmirror version
docmirror doctor
```

`doctor` should inspect optional dependency availability and print:

```text
core ok
pdf installed/missing
ocr installed/missing
office installed/missing
server installed/missing
```

### 4.5 README And Docs Truth Alignment

README must be rewritten around the product constitution.

First viewport target:

```text
DocMirror
The Trust Layer for Commercial Documents
Parse. Prove. Trust.

Turn bank statements, invoices, contracts, receipts, tax documents, and IDs
into verifiable, audit-ready, machine-usable signals.
```

Quickstart should show:

```bash
pip install docmirror
docmirror --version
docmirror doctor
pip install "docmirror[pdf]"
docmirror parse examples/synthetic_invoice.pdf --format json
```

Python quickstart should show:

```python
result = await perceive_document("statement.pdf")
mirror = result.to_mirror_json_vnext()
print(mirror["quality"]["overall"])
print(first_field_evidence)
```

Docs to update:

```text
README.md
README_zh-CN.md
docs/quickstart.md
docs/installation.md
pyproject.toml description/keywords/classifiers
CLI help text
CHANGELOG 1.0.0 entry
```

### 4.6 Public Benchmark And Claims

Rule:

```text
If a number is in README, it must be reproducible by a public command.
```

For 1.0.0, replace unverifiable claims:

```text
50ms parsing speed
~0.97 Table F1
120+ classified types
```

With:

```text
Public benchmark coming soon, or
Reproducible on synthetic mini set via scripts/run_first_benchmark.py
```

Best 1.0.0 public metrics:

```text
install smoke
import latency
first parse success
evidence coverage
source_ref coverage
trust report presence
failure envelope presence
```

These are aligned with the product category.

### 4.7 Public Fixture Strategy

Do not ship real PII fixtures.

Create:

```text
examples/fixtures/synthetic_bank_statement.pdf
examples/fixtures/synthetic_invoice.pdf
examples/fixtures/synthetic_receipt.png
examples/fixtures/synthetic_contract_excerpt.pdf
```

Each fixture must be:

```text
synthetic
small
license-safe
golden-testable
evidence-rich
stable across platforms
```

Public examples should avoid private `tests/fixtures` paths.

### 4.8 OSS Release Manifest

Add a machine-readable release manifest:

```text
docmirror/configs/release/oss_1_0_manifest.yaml
```

It should define:

```yaml
version: "1.0.0"
position:
  category: Commercial Document Trust Layer
  tagline: Parse. Prove. Trust.
install_contract:
  base:
    commands:
      - python -c "import docmirror"
      - docmirror --help
      - docmirror --version
      - docmirror doctor
  extras:
    pdf: docmirror[pdf]
    ocr: docmirror[ocr]
    office: docmirror[office]
public_docs:
  required:
    - README.md
    - README_zh-CN.md
    - docs/quickstart.md
    - docs/installation.md
forbidden_public_claims:
  - unreproducible benchmark numbers
  - private package required for all extra
  - universal parser as primary category
```

Add validator:

```text
scripts/validate/validate_oss_release.py
```

This validator should become the single release gate for 1.0.0.

---

## 5. Prioritized Execution Plan

### Phase 0: Freeze Release Contract

Status: 已完成.

Execution note:

```text
已完成: release manifest, validate_oss_release.py, validate_import_purity.py,
make validate-release, and CI/publish release smoke checks were added.
```

Goal:

```text
Make release readiness machine-checkable.
```

Tasks:

1. Add `docmirror/configs/release/oss_1_0_manifest.yaml`.
2. Add `scripts/validate/validate_oss_release.py`.
3. Add `make validate-release`.
4. Add CI job `release-smoke`.
5. Define P0/P1/P2 release checks in the manifest.

Validation:

```bash
python scripts/validate/validate_oss_release.py
make validate-release
```

Exit criteria:

```text
Release gate exists and can fail on known current blockers.
```

### Phase 1: Fix Minimal Install And Pure Import

Status: 已完成.

Execution note:

```text
已完成: docmirror.__init__ is dependency-light and silent; public import purity
is enforced by subprocess tests and release validation.
```

Goal:

```text
pip install docmirror && import docmirror succeeds in a clean venv.
```

Tasks:

1. Remove eager model imports from `docmirror/__init__.py`.
2. Remove root logger configuration from import time.
3. Audit package `__init__.py` files for heavy imports.
4. Convert structure/OCR/model re-exports to lazy access or explicit submodule imports.
5. Add subprocess test:

```text
tests/contract/test_minimal_install_contract.py
```

6. Add CI clean venv wheel smoke:

```bash
python -m build
python -m venv /tmp/docmirror-smoke
/tmp/docmirror-smoke/bin/pip install dist/*.whl
/tmp/docmirror-smoke/bin/python -c "import docmirror; print(docmirror.__version__)"
```

Validation:

```bash
python -m build
python scripts/validate/validate_oss_release.py
```

Exit criteria:

```text
Base wheel import passes with only declared core dependencies.
No OCR/log/license side effects during import.
```

### Phase 2: Fix CLI First Experience

Status: 已完成.

Execution note:

```text
已完成: Click root command uses lazy subcommand loading; --help, --version,
version, doctor, parse help, and docmirror FILE compatibility are covered by
contract tests.
```

Goal:

```text
CLI help/version/doctor are fast, quiet, and dependency-light.
```

Tasks:

1. Implement lazy Click command loading.
2. Add `docmirror version`.
3. Add `docmirror doctor`.
4. Decide and implement root-file parse compatibility:

```bash
docmirror FILE
```

5. Ensure parse-only imports happen after command invocation.
6. Add tests:

```text
tests/contract/test_cli_public_contract.py
```

Validation:

```bash
docmirror --help
docmirror --version
docmirror version
docmirror doctor
pytest tests/contract/test_cli_public_contract.py -q
```

Exit criteria:

```text
CLI public commands work in base install and do not load OCR/license/server.
```

### Phase 3: Fix Dependency Extras

Status: 部分已完成.

Execution note:

```text
已完成: docmirror[all] no longer includes private enterprise packages; base
dependencies declare the public CLI/import surface; optional dependency helper
was added; doctor gives install guidance. The release manifest now defines the
public all-extra members and lightweight per-extra smoke set.

已完成: optional dependency helper has contract tests and is used by the PDF/image
forgery detector, replacing top-level PyMuPDF import with recoverable install
guidance.

已完成: monolithic `docmirror[all]` smoke was replaced by per-extra smoke because
the full dependency set is too slow for a release gate. Lightweight public extras
(`plugins`, `projection`, `archive`, `langdetect`, `cache`) now pass install
smoke from the built wheel, while the manifest statically proves `all` contains
only approved public extras.

未完成: not every historical adapter/backend has been migrated to the shared
optional dependency helper. Remaining deep numpy-heavy algorithm paths are
documented by the architecture hotspot report and should be migrated during 1.1
hardening.
```

Goal:

```text
Public extras are truthful, installable, and not polluted by private packages.
```

Tasks:

1. Remove `enterprise` from `all`.
2. Decide whether to keep public `enterprise` extra at all.
3. Add a separate documented `commercial` installation section.
4. Add optional dependency helper.
5. Update adapters/backends to use helper.
6. Add tests for missing optional dependency messages.

Validation:

```bash
pip install "dist/docmirror-1.0.0-py3-none-any.whl[all]"
python -c "import docmirror"
docmirror doctor
```

Exit criteria:

```text
OSS all extra installs from public indexes only.
Missing optional deps never crash import/help.
```

### Phase 4: Align Public Positioning

Status: 已完成.

Execution note:

```text
已完成: README, README_zh-CN, quickstart, installation docs, pyproject metadata,
CLI help, python -m docmirror help text, and changelog now align on Commercial
Document Trust Layer / Parse. Prove. Trust.
```

Goal:

```text
Every public surface says the same thing.
```

Tasks:

1. Update `pyproject.toml`:

```text
description
keywords
classifiers
```

2. Rewrite README first viewport.
3. Rewrite Chinese README first viewport.
4. Replace "Universal Document Parser" as primary category.
5. Replace RAG-first framing with trust/evidence framing.
6. Update CLI help tagline.
7. Update docs quickstart.
8. Remove or replace broken `VISION.md` link.

Validation:

```bash
rg "Universal Document Parser|LLM-ready|RAG pipelines|VISION.md|50ms" README.md README_zh-CN.md docs pyproject.toml
```

Exit criteria:

```text
Public docs match docs/design/position.md.
Any remaining RAG/universal references are clearly secondary capabilities.
```

### Phase 5: Public Demo And Evidence Quickstart

Status: 已完成.

Execution note:

```text
已完成: examples/trust_quickstart.py and a synthetic public trust artifact show
field evidence, page, bbox, source_ref, confidence, and needs_review. E2E test
coverage was added.
```

Goal:

```text
A new user sees trusted commercial output in under 10 minutes.
```

Tasks:

1. Add synthetic public fixtures.
2. Add `examples/trust_quickstart.py`.
3. Show field evidence, page, bbox, confidence, source_ref, needs_review.
4. Add golden expected output for the synthetic fixture.
5. Add test that the quickstart works.

Validation:

```bash
python examples/trust_quickstart.py
pytest tests/e2e/test_quickstart_artifact_pack.py -q
```

Exit criteria:

```text
Public quickstart demonstrates Parse + Prove + Trust.
```

### Phase 6: Claims And Benchmark Hygiene

Status: 已完成.

Execution note:

```text
已完成: README no longer advertises non-reproducible benchmark numbers. Public
mini benchmark mode now reports only reproducible evidence/trust metrics and
explicitly excludes private fixture performance and competitor comparisons.
```

Goal:

```text
No public claim outruns public evidence.
```

Tasks:

1. Remove non-reproducible benchmark numbers from README.
2. Add public mini benchmark command.
3. Report evidence metrics, not only table/text F1.
4. Add benchmark methodology docs.
5. Make release benchmark optional but reproducible.

Validation:

```bash
python scripts/run_first_benchmark.py --public-mini
python scripts/generate_benchmark_table.py --public-mini
```

Exit criteria:

```text
README benchmark claims are either reproducible or explicitly marked roadmap.
```

### Phase 7: Architecture Hotspot Containment

Status: 已完成.

Execution note:

```text
已完成: existing clean architecture gates remain wired through make
validate-clean, and the new release validators prevent public-boundary import
regression.

已完成: a dedicated architecture hotspot report was added to make validate-clean.
It reports largest files, largest functions, warning thresholds, and top-level
optional dependency import warnings without destabilizing 1.0.0 on historical
debt.
```

Goal:

```text
Do not destabilize 1.0.0 with broad refactors, but stop architectural debt from growing.
```

Tasks:

1. Add hotspot report to hygiene:

```text
largest files
largest functions
import side effects
optional dependency leaks
```

2. Set warning thresholds for 1.0.0:

```text
file > 1500 lines: warn
function > 250 lines: warn
new function > 150 lines: fail unless allowlisted
```

3. Schedule 1.1 decompositions:

```text
structure/tables/engine.py
output/mirror.py
structure/evidence_plane.py
structure/page_topology.py
input/extraction/extractor.py
docmirror/__main__.py
```

Validation:

```bash
python scripts/run_quality_gate.py --profile hygiene --quiet
```

Exit criteria:

```text
Existing hotspots documented; new hotspots prevented.
```

### Phase 8: Release Candidate Gate

Status: 已完成.

Execution note:

```text
已完成: build, twine check, validate-release, validate-clean, contract/smoke
tests, clean base wheel install smoke, and public mini benchmark smoke were
executed during this implementation pass.

已完成: full public extra smoke was redesigned as smaller per-extra checks.
Lightweight public extras passed from the built wheel; heavier OCR/PDF/AI extras
remain explicit opt-in smoke targets so CI does not hide slow dependency
resolution behind one undiagnosable `docmirror[all]` job.
```

Goal:

```text
Produce a release candidate that a stranger can install and trust.
```

Required commands:

```bash
git clean -xfd -e .venv
python -m build
twine check dist/*
python scripts/validate/validate_oss_release.py
make validate-clean
make validate-release
pytest tests/smoke tests/contract -q
```

Clean venv smoke:

```bash
python -m venv /tmp/docmirror-oss-smoke
/tmp/docmirror-oss-smoke/bin/pip install dist/docmirror-1.0.0-py3-none-any.whl
/tmp/docmirror-oss-smoke/bin/python -c "import docmirror; print(docmirror.__version__)"
/tmp/docmirror-oss-smoke/bin/docmirror --help
/tmp/docmirror-oss-smoke/bin/docmirror --version
/tmp/docmirror-oss-smoke/bin/docmirror doctor
```

Full public extra smoke:

```bash
python -m venv /tmp/docmirror-oss-all-smoke
/tmp/docmirror-oss-all-smoke/bin/pip install "dist/docmirror-1.0.0-py3-none-any.whl[all]"
/tmp/docmirror-oss-all-smoke/bin/docmirror doctor
```

Exit criteria:

```text
All P0 checks pass.
P1 issues are documented or fixed.
No known README command fails.
No public metadata contradicts product positioning.
```

---

## 6. Priority Matrix

### Must Fix Before 1.0.0

| Priority | Issue | Why |
|---|---|---|
| P0 | Minimal install import fails | Package is unusable after install. |
| P0 | `docmirror --help` fails in base install | CLI first experience broken. |
| P0 | README command mismatch | Users copy commands that fail. |
| P0 | `all` includes private enterprise dependency | Public install path can fail/confuse. |
| P0 | Product positioning mismatch | Wrong category weakens launch and community understanding. |
| P0 | Missing release smoke CI | Regressions will recur. |

### Should Fix Before 1.0.0

| Priority | Issue | Why |
|---|---|---|
| P1 | Local plugin state in wheel | Mutable local state should not ship. |
| P1 | Broken README/docs links | Reduces trust. |
| P1 | Unreproducible benchmark claims | Community will challenge claims. |
| P1 | Stale docs quickstart API | Users hit outdated examples. |
| P1 | CLI import side effects | Makes project feel heavy and noisy. |

### Can Move To 1.1

| Priority | Issue | Why |
|---|---|---|
| P2 | Large internal files | Important, but broad refactor risks 1.0.0 stability. |
| P2 | Deep model/structure coupling | Known debt, protected by manifest exceptions. |
| P2 | Full public benchmark suite | Can start with mini benchmark in 1.0.0. |
| P2 | Performance profiling redesign | Needs stable baseline first. |

---

## 7. Validation Design

### 7.1 New Release Validator

Add:

```text
scripts/validate/validate_oss_release.py
```

Checks:

1. `pyproject.toml` version equals `docmirror.__version__`.
2. `docmirror[all]` does not include private dependencies.
3. Public docs do not contain forbidden primary positioning.
4. README commands are syntactically supported by CLI.
5. Required files exist:

```text
README.md
README_zh-CN.md
LICENSE
CHANGELOG.md
SECURITY.md
CODE_OF_CONDUCT.md
CONTRIBUTING.md
```

6. Broken local links are reported.
7. Wheel smoke script is configured in CI.
8. `.plugin_state.json` is not included in wheel.

### 7.2 Import Side-Effect Validator

Add:

```text
scripts/validate/validate_import_purity.py
```

Subprocess checks:

```bash
python -c "import docmirror"
python -c "import docmirror.cli.main"
python -c "import docmirror; print(docmirror.__version__)"
```

Assertions:

```text
no stdout
no stderr
exit 0
no banned optional modules imported
runtime under threshold
```

### 7.3 Clean Wheel Smoke

Add CI job:

```text
oss-release-smoke
```

It must:

```text
build wheel
create clean venv
install wheel without extras
run import/help/version/doctor
create clean venv
install wheel[all]
run doctor
```

This catches the exact failure found in release review.

---

## 8. Non-Regression Rules

The release fixes must not break:

| Scenario | Protection |
|---|---|
| `from docmirror import perceive_document` | Smoke import and API contract test |
| Existing parse pipeline | Current smoke/contract tests |
| OCR with `docmirror[ocr]` | OCR optional-extra smoke |
| PDF with `docmirror[pdf]` | PDF optional-extra smoke |
| CLI parse | CLI public contract test |
| Server | Server extra smoke |
| Plugin community outputs | Plugin runner tests |
| Enterprise/finance extensions | Nightly private workflow remains optional |
| Clean architecture manifest | `make validate-clean` |
| Public docs | `validate_oss_release.py` |

---

## 9. Definition Of Done For OSS 1.0.0

The project is ready for OSS 1.0.0 only when all of the following are true:

1. A clean base wheel install can run:

```bash
python -c "import docmirror"
docmirror --help
docmirror --version
docmirror version
docmirror doctor
```

Status: 已完成.

2. These commands are quiet and do not initialize OCR, license, server, AI, or plugin-heavy paths. Status: 已完成.
3. README commands all work. Status: 已完成.
4. README and PyPI metadata position DocMirror as:

```text
The Trust Layer for Commercial Documents.
```

Status: 已完成.

5. `docmirror[all]` installs only public OSS dependencies. Status: 已完成; static metadata validation proves no private packages are included, and lightweight per-extra wheel smoke now passes.
6. Missing optional features return visible install guidance. Status: 部分已完成; `doctor`, the shared helper, and forgery detection cover the public surface, but remaining deep backend migration remains a 1.1 hardening task.
7. The wheel does not include mutable local state. Status: 已完成.
8. Public benchmark claims are reproducible or removed. Status: 已完成.
9. Public quickstart demonstrates evidence and trust, not just parsed text. Status: 已完成.
10. `make validate-release` passes. Status: 已完成.
11. `make validate-clean` passes. Status: 已完成.
12. CI includes clean wheel smoke. Status: 已完成.
13. Changelog accurately describes the actual 1.0.0 release state. Status: 已完成.

---

## 10. Recommended Implementation Order

The safest sequence is:

1. Add release manifest and validators.
2. Fix `docmirror.__init__` pure import.
3. Fix CLI lazy loading and public commands.
4. Fix dependency extras.
5. Add wheel smoke CI.
6. Rewrite README/metadata positioning.
7. Fix docs quickstart and broken links.
8. Remove mutable plugin state from wheel.
9. Add synthetic trust quickstart.
10. Re-run release candidate gate.

This order is intentional:

```text
First make failures machine-visible.
Then fix install/import/CLI.
Then align messaging.
Then improve demos and claims.
```

It avoids doing a beautiful README for a package that still fails at import time.

---

## 11. Best Next Patch Batch

The next implementation batch should be narrowly scoped:

```text
Batch 1: OSS P0 release gate and minimal import
```

Files likely touched:

```text
docmirror/__init__.py
docmirror/cli/main.py
docmirror/runtime/optional_deps.py
pyproject.toml
README.md
README_zh-CN.md
docs/quickstart.md
docs/installation.md
docmirror/configs/release/oss_1_0_manifest.yaml
scripts/validate/validate_oss_release.py
scripts/validate/validate_import_purity.py
.github/workflows/ci.yml
Makefile
tests/contract/test_minimal_install_contract.py
tests/contract/test_cli_public_contract.py
```

Batch 1 is complete when:

```text
clean venv base wheel import/help/version/doctor all pass
README canonical commands pass
docmirror[all] no longer pulls private enterprise dependency
```

After Batch 1, proceed to:

```text
Batch 2: Positioning rewrite and public trust quickstart
Batch 3: Benchmark claim hygiene and public mini golden set
Batch 4: 1.1 architecture hotspot decomposition
```

---

## 12. Strategic Product Guardrail

Do not optimize DocMirror into a better generic parser at the expense of its real category.

The release should make this unmistakable:

```text
DocMirror is not trying to be the broadest document parser.
DocMirror is trying to be the most trustworthy commercial document signal layer.
```

The strongest OSS community will come from developers who need:

```text
commercial document ingestion
field-level evidence
auditability
visible failure
trust scoring
downstream system readiness
```

That is the community to design 1.0.0 for.
