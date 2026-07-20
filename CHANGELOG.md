# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- A concise primary CLI including `docmirror -v`, `-p/--pages`, `-t/--doc-type`, `-r/--recursive`, and `-q/--quiet`.
- Simple `--community`, license-aware `--all`, and complete `--audit` output modes.
- Top-level `license` and `ocr` commands, default plugin listing, and `--help-all` for advanced parse options.

### Changed
- Bare file CLI invocations now persist both canonical Mirror and Community JSON while API and SDK defaults remain unchanged.
- Finance and Enterprise outputs selected by `--all` are limited to editions authorized by the active license and installed extension packages.
- Superseded compatibility commands and output-selection flags were removed so the public CLI has one canonical syntax.

## [1.0.8] — 2026-07-19

This Python distribution release consolidates the backward-compatible Mirror
JSON updates through 1.0.7 and hardens every public release trust surface.

### Added
- Daily main-branch CI and a release gate requiring 14 complete UTC days with at least one successful main CI run per day and no completed failures.
- Public, versioned JSON Schemas and CI-built source previews for the Go, Java, TypeScript, and MCP integrations.
- GitHub release notes and isolated wheel installation checks that assert the installed runtime version.

### Changed
- The Python distribution, CLI, REST metadata, observability context, licensing client metadata, and release manifest now report version 1.0.8 from a consistent release source.
- Nightly workflows report missing private samples as an explicit skip instead of a product failure.
- Public documentation and package metadata use reachable GitHub Pages, repository, issue, changelog, and schema links; unavailable hosted API and unpublished registry SDK claims were removed.
- The unpublished `docmirror-enterprise` dependency was removed from the public PyPI extras metadata; private editions remain outside the OSS wheel.
- The PyPI publishing workflow now requires an exact `v1.0.8` identity on the current `main` commit and uses trusted publishing after the release gate passes.
- Version 1.0.8 uses a one-time, owner-approved immediate-release policy after its PR and current-main checks passed; later versions continue to require the 14-complete-day green window.

### Fixed
- Release archive validation no longer hard-codes version 1.0.0 and now inspects the version declared by the release manifest.
- Community projections include the precision, evidence, reconciliation, completeness, and readability fixes shipped in Mirror JSON 1.0.1 through 1.0.7.

### Security
- Public wheel validation excludes private packages, fixtures, environment files, build artifacts, internal reports, and private plugin state.
- Release uploads use PyPI trusted publishing with a protected GitHub environment and short-lived OIDC credentials.

## [Mirror JSON 1.0.7] — 2026-07-19

This is a backward-compatible Community precision and readability patch for
credit reports and the shared 6+1 consumer projection. The Community envelope
remains version 2.2, and the Python distribution version remains 1.0.0.

### Added
- Subtype-aware Community extraction for native personal brief reports, scanned personal detailed reports, and native enterprise credit reports, including canonical account, credit-line, repayment, overdue, inquiry, public-record, and summary collections.
- Stable credit-business identifiers, normalized record views, source evidence, conflict resolution, reconciliation checks, document-completeness auditing, and privacy-safe golden governance that prevents unsupported 100% precision claims.
- A shared reference-only Community reading view for all six core plugins and Generic fallback using ordered `sections`, `tables`, `notes`, and `document_flow` structures.

### Changed
- Community credit-report classification now records report subtype and content mode, recovers validated header identity, and applies profile-specific collection requirements without weakening backward compatibility.
- Reading tables point to canonical collections with `data_ref`; Generic multi-table output uses stable `record_ids`, and business-license notices use `content_ref` while retaining legacy fields and sections.
- Section ordering now carries logical and source page ranges, while the common post-extract hook normalizes the same reading contract across bank statements, WeChat Pay, Alipay, VAT invoices, business licenses, credit reports, and Generic documents.

### Fixed
- Native credit reports no longer lose account histories, credit lines, inquiry records, public records, or summary facts when source tables are borderless or represented as narrative text.
- Scanned detailed reports preserve repayment-grid and local account-structure evidence, flag truncated source documents for review, and avoid treating positional placeholder rows as canonical business records.
- Reading metadata no longer duplicates business rows or leaks into the dataset catalog; every flow reference, data pointer, content reference, and Generic record reference is validated against its canonical target.

## [Mirror JSON 1.0.6] — 2026-07-19

This is a backward-compatible precision and reviewability patch for scanned
Generic documents. The Community JSON structure and data flow remain unchanged,
and the Python distribution version remains 1.0.0.

### Added
- Public `--page-split auto|off|force` control and a concise post-parse Community summary showing the selected plugin, document type, quality score, readiness, warning count, and prioritized review messages.
- Generic fallback review signals with table-, row-, and page-level targets for weak provenance, repaired headers, failed normalization, uncertain currencies, suspicious row alignment, and low-confidence text-table recovery.
- Exact JSON-contract, CLI, table-reconstruction, Generic projection, private native-PDF, and full 87-page scanned-audit regression coverage.

### Changed
- Generic fallback now uses stricter header selection, table-local type inference, table-local currency context, conservative amount normalization, appendix-aware field confidence, and evidence-aware duplicate table handling.
- Scanned report processing now confirms sideways OCR orientation before reserving split-page numbers and uses numeric row evidence to separate tokens trapped in falsely merged vertical cells.
- Review output now aggregates repeated repaired-header warnings with priority pages while retaining precise record targets for actionable anomalies.

### Fixed
- Open-border scanned tables retain unruled label columns and restore missing outer boundaries without changing the downstream table or Community JSON contracts.
- Multi-level scanned headers no longer absorb the first body amount when a horizontal rule is missing; the audited inventory value `1,297,676.15` is restored to both book-balance and book-value columns.
- Data-contaminated rows are no longer promoted as headers, unambiguous OCR thousands-separator errors normalize safely while preserving raw text, and signature/seal appendix fields remain available with review-level confidence.

## [Mirror JSON 1.0.5] — 2026-07-18

This is a backward-compatible precision patch for the Community core-domain
projections. The Python distribution version remains 1.0.0.

### Added
- Conservative Community precision guards for required-field coverage, normalization, duplicate transaction identifiers, VAT amount reconciliation, business-license identifiers, and credit repayment anchors.
- Positioned Mirror-atom recovery for complete 13-column bank ledgers, complete 8-column WeChat Pay and Alipay exports, and complete 9-column VAT invoice line items.
- High-confidence local visual recovery for business-license copy type, QR presence, national emblem and registration seal, plus VAT QR payload and seller-seal presence.

### Changed
- Bank parser selection now prefers equally complete positioned tables when they preserve more source columns, while retaining transaction references, counterparty bank details, channel, purpose, and summary data.
- Payment projections now retain every source column, preserve non-counted directions, and recover certificate, account-holder, account, identity, period, scope, currency, and unit metadata from positioned first-page text.
- VAT projection now recovers invoice header, buyer and seller identity/contact/bank fields, password and remarks areas, participants, amount-in-words, visual facts, and fully structured line items.
- Business-license projection now removes OCR notice and stamp contamination, restores guarded standard notice and authority content, preserves partially visible registration dates, and validates visible document objects without inventing occluded text.

### Fixed
- Summary-row filtering no longer drops valid payment rows whose direction is income or expense.
- Bank recovery no longer collapses split debit/credit tables into a narrower legacy layout or deduplicates distinct transactions that share lossy business fields.
- Community readiness now moves to review when precision warnings reveal malformed, incomplete, duplicated, or invariant-breaking domain data.

## [Mirror JSON 1.0.4] — 2026-07-17

This is a backward-compatible patch release of the Mirror JSON contract. The
Python distribution version remains 1.0.0.

### Added
- A consumer-first Community 6+1 projection for bank statements, WeChat Pay, Alipay, VAT invoices, business licenses, credit reports, and the universal fallback.
- A compact Community 2.2 consumer contract with canonical field values, reference-only field details and datasets, masking-aware dictionaries, structured operational issues, and 2.0/2.1 schema compatibility.
- Adaptive generic fallback recovery for text-derived KV fields, typed and normalized values, identity semantics, outlines, table descriptors, repeated date-led rows, and structure-projected records.
- Bilingual word-split recovery for payment ledgers, business licenses, and VAT invoices, including English VAT amount reconciliation and line-item extraction.

### Changed
- `data.fields` is the sole normalized-value location; `field_details` carries `value_ref`, evidence, confidence, review state, and only materially different raw text.
- Dataset descriptors use JSON Pointer references without embedding rows, while record-column schemas are referenced instead of serialized twice.
- VAT line items are the single canonical invoice-row collection, `invoice_date` is the single invoice-date field, and generic recovered rows live only in `data.records`.
- Domain validation gaps live only in `validation.domain_contract`; intermediate field metadata and VAT provenance copies are folded into `data.field_details`.
- Business output retains semantic summaries, key metrics, and genuinely derived dimensions while omitting presentation descriptors, direct field copies, metric cards, and mirrored readiness values.
- Single-plugin Community outputs use only `plugin`; `plugins` is reserved for real multi-plugin compositions.
- Community serialization consumes plugin-owned DEC extensions before removing generic intermediate metadata and duplicated structures from the final artifact.

### Fixed
- Unclassified `unknown` and `generic` documents now execute the universal Community plugin instead of being skipped.
- Payment KV fallback metadata, credit-report subject naming, and scanned repayment-grid extraction now align with the Community domain contracts.
- Removed the duplicate top-level credit-report repayment collection; `data.repayment_records` is its single public location.

## [Mirror JSON 1.0.3] — 2026-07-17

This is a backward-compatible patch release of the Mirror JSON contract. The
Python distribution version remains 1.0.0.

### Added
- A concise `--mirror` CLI flag that explicitly persists the canonical `_mirror.json` diagnostic artifact.
- Cross-surface delivery contracts covering Community-only defaults, explicit Mirror output, output profiles, task manifests, and support artifact packs.

### Changed
- `perceive_document()` now returns the canonical runtime `ParseResult` directly; the redundant `PerceiveResult` wrapper and its duplicate result path have been removed.
- Mirror JSON and all edition plugins now project from the same `ParseResult` source of truth, with any runtime Mirror cache kept private and non-contractual.
- Open-source CLI, REST, Task API, SDK, and work-unit planning now default deterministically to Community JSON only; entitlement state no longer changes implicit outputs.
- The public quickstart profile now produces only open-source Mirror and Community projections plus support artifacts, while enterprise and finance outputs remain explicitly requested extensions.
- Common CLI help now emphasizes the default Community workflow and hides advanced compatibility controls without removing them.

### Fixed
- Support artifacts can now consume the in-memory Mirror projection without requiring `_mirror.json` to be persisted.
- CLI export and completion reporting now use the Community artifact when Mirror output is not requested.

## [Mirror JSON 1.0.2] — 2026-07-17

This is a backward-compatible patch release of the Mirror JSON contract. The
Python distribution version remains 1.0.0.

### Added
- Deterministic OCR safe correction for Chinese field labels, controlled English terms, typed values, and checksum-valid identifiers without an LLM dependency.
- Context-scoped correction dictionaries, weighted OCR-confusion matching, `safe` / `suggest` / `off` execution controls, and correction audit indexes in Mirror evidence.
- Versioned locale/domain correction packs with conflict validation, opt-in customer packs, script-aware tokenization, country validator registration, and language/country/locale controls across CLI, REST, Task API, and SDK.
- `docmirror ocr-correction` maintenance commands for pack validation, decision explanation, golden-corpus evaluation, and reviewable JSONL candidate export.

### Changed
- Scanned PDF, image fallback, universal OCR, and reconstructed-table paths now share one conservative correction policy while preserving original OCR text, confidence, geometry, and source references.
- Correction audit events now include the selected packs, pack version, locale/script, candidate scores, and uniqueness margin.

### Fixed
- Preserved OCR confidence when routing universal OCR words into scanned-table reconstruction.
- Prevented unconditional alphanumeric substitutions such as product-code `S` to digit `5` and lowercase `1` to `l`.

## [Mirror JSON 1.0.1] — 2026-07-16

This is a backward-compatible patch release of the Mirror JSON contract. The
Python distribution version remains 1.0.0.

### Added
- Automatic scanned-spread decomposition before OCR, with source-crop provenance, invertible coordinate transforms, and an explicit `--page-split` control.
- Bordered-table reconstruction for scanned documents, including row/column bands, validated merged-cell spans, token-to-cell assignment, and compact physical-to-logical table references.
- Durable `/v1/tasks` and `/v1/tasks/batch` APIs with status polling, isolated per-file artifacts, partial-failure handling, and safe artifact downloads.
- Quality gates for table-grid integrity, physical-table reference integrity, and source-text conservation.
- A real credit-report regression covering six physical scans expanded into eleven logical pages, 31 tables, evidence conservation, payload volume, and relationship integrity.

### Changed
- Mirror table geometry now has a single evidence owner per table; other cells retain only local geometry and provenance.
- Standard page projections and logical-table provenance are compact references instead of repeated full table payloads.
- Headerless tables now contribute their content to structured text, while the CLI reports raw extracted text and structured text separately.
- Credit-report Mirror output no longer emits a bank-statement business view; domain formatting remains the responsibility of downstream editions.
- Task execution now uses durable manifests, runtime-resolved output roots, stable artifact maps, and gateway fallback reporting.

### Fixed
- Rejected non-rectangular, full-grid, and divider-crossing merge candidates that produced overlapping table cells.
- Eliminated empty table evidence atoms, repeated table-wide metadata, duplicated physical-table references, and self-referential graph edges.
- Restored all 1,640 unique OCR source references for the credit-report fixture while reducing the affected Mirror payload from approximately 73 MB to 8.5 MB.
- Restored headerless-table text that had reduced the CLI extracted-text result from approximately 12k characters to 4.5k characters.
- Corrected VLM gateway fallback collection, credit-report hook invocation compatibility, task-route availability, and cross-format validation compatibility.

## [1.0.0] — 2026-06-30

### Added
- **Formula Recognition GA**: Complete F1–F12 formula type coverage with full test golden gates
- **vNext 1.0 Mainline Readiness**: added release gates for removed legacy references, vNext mirror volume, UDTR golden metadata, and cross-format readiness
- **PageProjection Topology Gates**: promoted the page-centric topology track from PCM/page-canvas naming to vNext PageProjection contracts
- **Privacy Guard Patterns**: `.gitignore` hardened — `!docs/design/` negation bug fixed; credential, fixture, and private-path patterns added
- **OSS Release Gate**: `validate-release` now checks public metadata, pure imports, release manifest requirements, and built archive boundaries
- **Public Trust Quickstart**: synthetic dependency-light artifact and example demonstrate field evidence, bbox, confidence, source refs, and review status

### Changed
- Public positioning now consistently uses **Commercial Document Trust Layer** and **Parse. Prove. Trust.**
- CI now runs the active vNext removed-reference and mirror-volume gates instead of deleted PCM-era validators
- Release-blocking `make lint` now covers ruff, formatting, and clean-architecture gates; full mypy remains available as `make typecheck` for non-blocking type-debt audits
- Optional extras smoke validation now prints per-extra progress and uses quieter, non-interactive pip installs
- `docmirror`, `docmirror --help`, `docmirror --version`, `docmirror version`, and `docmirror doctor` are dependency-light first-run surfaces
- `docmirror[all]` is limited to public OSS extras; commercial/enterprise packages remain separate

### Removed
- Dormant public benchmark publishing workflows and scripts until the benchmark suite is reproducible from public artifacts.

### Fixed
- TQG regression compatibility for vNext mirror payloads, conservation-oracle payload synthesis, scanned micro-grid column expectations, and schema fixture directory discovery
- Classification keyword coverage for newly promoted document scenes used by the release regression track

### Security
- Final OSS boundary pass: `docs/design/` and all private fixture references removed from git tracking
- Mutable local plugin state is excluded from release wheels

---

## [0.9.0] — 2026-06-10

### Added
- **EFMP Extension Points**: Extension point framework and mirror geometry conservation contract gates
- **Core Mirror Geometry Precision**: Spatial accuracy improved to pass contract gate validation
- **Hygiene Allowlist Colocation**: All code hygiene tooling consolidated under `docmirror/tools/code_hygiene/`; removed from repo root
- **CCP Import Audit Report**: Fresh audit after all architecture gate fixes

### Changed
- Quality gate standard profile now passes with live progress UI during CI runs

### Fixed
- Quality gate CI stability

---

## [0.8.0] — 2026-06-03

### Added
- **Architecture A — Projection DAG**: Cross-page entity resolution through a projection directed-acyclic graph
- **Architecture A — VLM Gateway**: Integration point for Vision Language Model providers
- **Architecture A — CLI Contracts**: Enhanced command-line interface contract definitions
- **Unified Quality Gate System**: `run_quality_gate.py` with `standard` / `full` profiles and live progress UI
- **Code Hygiene Audit Program**: Automated import boundary checks, coding standard enforcement, dead code detection

### Changed
- **Output Pipeline**: Refactored for Architecture A — pure Core Mirror output, no intermediate format paths
- Architecture gate tests added for projection DAG, VLM gateway, and CLI contract conformance

---

## [0.7.0] — 2026-05-20

### Added
- **Mirror Layer Redesign — SSO / SPE / SDU**: Design 13 Phase 0–5 implementation:
  - **SSO** (Structured Super-Objects): Page-level structured content mirror — hierarchical block grouping with geometry
  - **SPE** (Spatial Page Entities): Page-level entity mapping — identity, institution, and value fields pinned to spatial regions
  - **SDU** (Spatial Document Units): Document-unit identity resolution — cross-page entity deduplication and reconciliation

### Changed
- Mirror output format upgraded to SSO/SPE/SDU contract; all downstream consumers (plugins, API, output builder) adapted
- Mirror frozen boundary hardened — no mutation after Orchestrator.enhance() completes

---

## [0.6.0] — 2026-05-06

### Added
- **Enterprise/Finance Plugins**: Alipay enterprise plugins with license entitlement integration
- **Plugin Licensing**: Online/offline license verification framework (`plugins/licensing/`)
- **TQG Manifest Validation**: Fixture-level compliance checks for real-world fixture cataloging

### Changed
- **Plugin Layout Restructure**: Community plugins moved from `plugins/` root into per-domain packages (`bank_statement/`, `wechat_payment/`, `alipay_payment/`, `vat_invoice/`, `business_license/`, `credit_report/`, `generic/`)
- **Docs History Purge**: `docs/` cleaned — only root-level markdown files tracked; internal design docs removed from git

### Fixed
- Zero-table bank ledger detection via LTRO pipe reconstruction
- Local-only PII fixtures exempted in TQG manifest validation (controlled exception for non-distributed test files)

### Removed
- **`docs/design/` directory** — internal design documents no longer tracked in the public repo
- **Private paths and PII** — entire git history scrubbed via `git filter-repo`

### Security
- OSS boundary tightened: `tests/fixtures/` fully gitignored; fixture provenance tracked in YAML registry instead
- PII-aware fixture compliance validation added to TQG platform

---

## [0.5.0] — 2026-04-22

### Added
- **Test Quality Gates (TQG) Platform**: Manifest-driven golden test validation framework (Design 10, Phase 0–4)
- **Core Pipeline Stages (CPS)**: Seven-stage directory layout implementing Design 12 CPA:
  - `entry/` — public API (`perceive_document`, `PerceiveOptions`, `PerceiveResult`)
  - `pipeline/` — `DocumentPipeline`, `PagePipeline`, `PdfSyncProcessor`
  - `segment/` — page segmentation and layout analysis
  - `extract/` — core extraction from parsed pages
  - `table/` — Table Normalization Pipeline (TNP) with generic and ledger profiles
  - `ocr/` — OCR pipeline (UOP) with built-in and external providers
  - `bridge/` — `ParseResultBridge` for core-to-mirror boundary crossings
- **CCP Layout Gates**: Core Consumer Contract enforcement — plugin import audits, god-file validators
- **Dual-View TQG Oracles**: Independent verification for borderless and structured table output

### Changed
- **CoreExtractor Slimmed**: Split into `PagePipeline` / `DocumentPipelineContext` behind CPS facade
- **Table/OCR Flows Consolidated**: TNP (Table Normalization Pipeline) and UOP (OCR Pipeline) replace scattered god-file implementations
- **Layout Helpers**: Moved from `core/layout` into `core/segment/`
- **Security Module**: Moved from `core/security` into `framework/` as a cross-cutting concern

### Fixed
- **WeChat 5111-row Regression**: Borderless-ledger TNP hooks with `generic` profile stripped on ledger documents; standalone tail-page quarantine metadata for large statements
- Golden extract gates all pass: 5111 logical rows, dual-view/quarantine TQG oracles, CPS/god-file validators
- Borderless-ledger performance toward sub-60s target

---

## [0.4.0] — 2026-04-08

### Added
- **Format Capability Registry (FCR)**: YAML-driven format/extension/MIME routing replacing hardcoded dispatch in `ParserDispatcher`
- **Middleware Execution Platform (MEP)**: Catalog-driven middleware registration:
  - `configs/yaml/middleware_catalog.yaml` — single source of truth for middleware class metadata
  - `configs/yaml/enhancement_profiles.yaml` — content-model-aware pipeline definitions with stage ordering
  - `configs/pipeline/registry.py` — profile resolution and middleware instantiation
- **Plugin DEC Migration (Phase 5)**: All community plugins migrated to Domain Extraction Contract
- **Models Layer Redesign (Design 09)**: Waves 1–3 — MOC (Mirror Object Contract), DEC (Domain Extraction Contract), DTI (Document Type Identity) fully implemented
- **Core Extract EPO**: Evidence-Preserving Output for borderless ledger row fidelity (5111/5111 row target achieved)
- **Unified PEC Runner**: Plugin Extraction Contract runner consolidating community/enterprise/finance plugin execution
- **Config Validation Tools**: `validate_format_capabilities.py`, `validate_middleware_catalog.py` for FCR/MEP correctness

### Changed
- **Config System Restructured**: All YAML consolidated under `configs/yaml/`; root `configs/` shim modules removed
- **6 Backward-Compat Config Shims Removed**: Imports migrated to `runtime/`, `pipeline/`, `scene/`, `domain/` subpackages across 23 files
- **Parse Cache Removed from Default Pipeline**: `framework/cache.py` retained for future API deployments but disabled; `--skip-cache` kept as no-op
- **Orchestrator Decoupled**: Middleware fully driven by FCR + MEP profiles, not hardcoded in `orchestrator.py`
- **DI Container**: `get_dispatcher()` / `get_orchestrator()` now delegate to process-wide singletons

### Fixed
- 51 targeted tests passed after config migration — zero regressions
- No remaining imports of deleted shim modules in source, tests, docs, or examples

---

## [0.3.1] — 2026-03-24

### Added
- SLM entity extraction pipeline with section-driven strategy (opt-in via `DOCMIRROR_ENABLE_SLM=1`)

---

## [0.3.0] — 2026-03-18

### Added
- RESTful API v1.0 overhaul with modern FastAPI patterns and ParseResult model
- Chinese README with language switcher (English | Chinese)
- Multi-provider OCR support infrastructure

### Changed
- Complete README rewrite — MinerU-inspired professional layout with dark/light mode, badges, and quick-start tables
- Demo data replaces real customer info in README samples
- All ruff lint/format errors fixed for CI compliance

### Removed
- Coverage badge (no Codecov token configured)

---

## [0.2.0] — 2026-03-12

### Added
- `--skip-cache` CLI flag for forcing full re-parse
- `scene` persisted as a Pydantic field on `PerceptionResult` (survives cache serialization)
- Trust scoring system: mirror fidelity validation with 7 artifact dimensions
- Image quality assessment with VLM recommendation flags
- Generic Validator with document-type-agnostic scoring dimensions
- Bilingual entity extraction (Chinese/English concatenated label-value patterns)
- 110 test cases with full pipeline coverage

### Changed
- Middleware pipeline simplified: removed ColumnMapper and Repairer
- Entity extraction reads from `enhanced.enhanced_data` (was incorrectly using `base_result.metadata`)
- vNext mirror output uses persisted scene metadata instead of transient enhancement attributes
- Block output cleaned: removed internal `markdown`/`bbox` fields from table blocks
- Empty image blocks (logos/stamps) filtered from API output

### Removed
- `docmirror/integrations/` — LangChain/LlamaIndex loaders (planned for future upstream PRs)
- `docmirror/middlewares/alignment/` — ColumnMapper and Repairer standardization logic
- `output_file` field from API response (CLI-only concern)
- `scripts/classify_docs.py` — unused standalone script

---

## [0.1.0] — 2026-03-10

### Added
- Initial open-source release of DocMirror
- 8 format adapters: PDF, Image, Word, Excel, PowerPoint, Email, Web, Structured
- Core extraction engine with PyMuPDF and pdfplumber backends
- OCR support via RapidOCR (ONNX Runtime)
- Layout analysis with DocLayout-YOLO and rule-based fallback
- Multi-strategy table extraction (character-based, PDFPlumber, RapidTable, VLM)
- Formula recognition via LaTeX-OCR
- PDF forgery & tamper detection (ELA + metadata analysis)
- VLM integration via Ollama HTTP API
- Middleware pipeline: classification, extraction, institution detection, validation
- Redis-based parse result caching
- `pyproject.toml` with modular optional dependencies
- Test suite with pytest
- GitHub Actions CI/CD (lint, test on Python 3.10-3.13, build)
- Apache 2.0 license
