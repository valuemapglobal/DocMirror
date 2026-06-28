# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-06-22

### Added
- **Formula Recognition GA**: Complete F1–F12 formula type coverage with full test golden gates
- **Privacy Guard Patterns**: `.gitignore` hardened — `!docs/design/` negation bug fixed; credential, fixture, and private-path patterns added

### Security
- Final OSS boundary pass: `docs/design/` and all private fixture references removed from git tracking

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
