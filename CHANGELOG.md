# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0] - 2026-06-18

### Removed
- **`DOCMIRROR_MIRROR_COMPAT` / v1 legacy shim**: mirror JSON no longer emits `document.micro_grids`, top-level `pages[].texts`, `document._deprecated`, or `meta.pcm_legacy_shim`
- `domain_specific._micro_grids` production write path (SSOT: `_page_evidence_bundles[].micro_grid_structures`)
- `domain_specific._scanned_*` read paths (legacy extractor metadata converted at bridge boundary only)
- `_compact_micro_grids_for_standard` document-level projection

### Changed
- **Breaking (PCM)**: Mirror JSON SSOT is `pages[n].regions[]` + `pages[n].flow`; forensic OCR deduped in `scanned_ocr_pages` with evidence refs only
- `ParseResult.to_api_dict` materializes `PageContent.page_canvas` via `sync_page_canvases()` before serialize
- `sections[]` gain `region_refs` and `page_span` when pages carry regions
- `pages[n].reading_order` interleaves `region_id` and `text:{index}` by vertical position
- `flow.texts` excludes lines mostly covered by region bboxes (Design 19 §4.4)

### Added
- **Page-Centric Mirror (PCM)**: `page_access`, `domain_access`, `page_canvas/` (models, build, detect, sync, flow_filter), `legacy_project`
- `_page_evidence_bundles` memory SSOT; `merge_micro_grid_structures_into_bundles`
- Offline migration: `tools/compat/fold_mirror_to_page_canvas.py`
- CI gates: `tools/gate_pcm_legacy_refs.py` (G2/G3), `tools/gate_pcm_mirror_volume.py` (G5/C2)
- TQG: `page_canvas.yaml`, `pcm_finance` oracle, scanned_micro_grid/local_structure oracles on `page_access`
- `records_from_micro_grid_dict` for repayment projection from region structures
- `scanned_page` writes `region_detect.region_detect_candidates` on evidence bundles
- `DOCMIRROR_PCM_LEGACY_ACCESS_DEBUG` for deprecated JSON path access counting (legacy file reads)

## [0.5.0] - 2026-06-01

### Changed
- Legacy import paths removed; use `core/entry/`, `core/segment/`, `core/extract/` directly

## [0.1.0] - 2026-03-11

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
- Middleware pipeline: SceneDetector, EntityExtractor, ColumnMapper, Validator, Repairer
- Redis-based parse result caching
- `pyproject.toml` with modular optional dependencies
- Test suite (28 tests) with pytest
- GitHub Actions CI/CD (lint, test on Python 3.10-3.13, build)
- Apache 2.0 license
