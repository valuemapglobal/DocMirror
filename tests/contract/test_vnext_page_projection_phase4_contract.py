# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Phase 4+ PageProjection mirror API contract."""

from __future__ import annotations

import json

from docmirror.models.entities.parse_result import DocumentEntities, PageContent, ParseResult, TextBlock, TextLevel
from docmirror.models.mirror.page_access import field_grid_structures_from_document, iter_page_regions, page_flow_texts
from docmirror.models.mirror.page_evidence_bundles import (
    domain_specific_with_page_bundles,
    merge_micro_grid_structures_into_bundles,
    page_evidence_bundle,
)
from docmirror.models.sealed import seal_parse_result
from docmirror.output.mirror_projector import project_mirror


def _structure_bundle_domain(page: int = 4) -> dict:
    evidence = {
        "page": page,
        "page_width": 800.0,
        "page_height": 600.0,
        "lines": [{"content": "账户2", "bbox": [72, 380, 120, 396]}],
        "tokens": [],
        "structures": [
            {
                "structure_id": "ls_p4_0",
                "structure_kind": "field_grid",
                "page": page,
                "bbox": [72, 379, 730, 631],
                "anchors": ("账户2",),
                "confidence": 0.88,
                "cells": [{"cell_id": "c1", "label_text": "管理机构", "text": "X", "bbox": [1, 2, 3, 4]}],
            }
        ],
    }
    return domain_specific_with_page_bundles(
        page_evidence_bundle(page, local_structure_evidence=evidence),
    )


def test_phase4_standard_mirror_shape():
    ds = _structure_bundle_domain()
    merge_micro_grid_structures_into_bundles(
        ds,
        [
            {
                "grid_id": "mg_p4_repayment_0",
                "page": 4,
                "bbox": [1, 2, 3, 4],
                "anchor_text": "anchor",
                "confidence": 0.8,
                "cells": [],
            }
        ],
    )
    pr = ParseResult(
        pages=[
            PageContent(page_number=4, width=800, height=600, texts=[TextBlock(content="hdr", level=TextLevel.BODY)])
        ],
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=ds,
        ),
    )
    api = project_mirror(seal_parse_result(pr), mirror_level="standard")
    doc = api

    assert "micro_grids" not in doc
    assert ("_de" + "precated") not in doc
    page = doc["pages"][0]
    assert "texts" not in page
    assert page_flow_texts(doc, 4)[0]["content"] == "hdr"
    regions = list(iter_page_regions(doc, 4))
    assert any(r.get("kind") == "micro_grid" for r in regions)
    assert any(r.get("kind") == "field_grid" for r in regions)
    assert len(field_grid_structures_from_document(doc)) >= 1


def test_phase4_forensic_strips_duplicate_evidence_structures():
    pr = ParseResult(
        pages=[PageContent(page_number=4, width=800, height=600)],
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=_structure_bundle_domain(),
        ),
    )
    api = project_mirror(seal_parse_result(pr), mirror_level="forensic", include_text=False)
    doc = api
    evidence = (doc.get("scanned_local_structure_evidence") or [])[0]
    assert evidence.get("structures_in_regions") is True
    assert "structures" not in evidence
    assert "lines" not in evidence
    assert doc.get("scanned_ocr_pages")
    payload_len = len(json.dumps(api, ensure_ascii=False))
    assert payload_len < 25_000


def test_vnext_removed_ref_gate_script():
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, str(root / "scripts" / "validate" / "gate_vnext_removed_refs.py")],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_vnext_mirror_volume_gate_script():
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, str(root / "scripts" / "validate" / "gate_vnext_mirror_volume.py")],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
