# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.core.ocr.page_canvas.evidence_bundles import (
    attach_page_evidence_bundles,
    build_page_evidence_bundles,
    bundles_from_legacy_extractor_meta,
    domain_specific_with_page_bundles,
    merge_micro_grid_structures_into_bundles,
    micro_grid_evidence_needing_reconstruction,
    page_evidence_bundle,
    upsert_page_evidence_bundle,
)
from docmirror.models.mirror.domain_access import (
    local_structure_evidence_pages_from_domain_specific,
    micro_grid_evidence_pages_from_domain_specific,
)


def test_build_page_evidence_bundles_returns_existing_bundles():
    ds = {
        "_page_evidence_bundles": [
            {
                "page": 4,
                "micro_grid_evidence": {"page": 4, "lines": []},
                "local_structure_evidence": {"page": 4, "structures": [{"structure_id": "ls_p4_0"}]},
            },
        ],
    }
    bundles = build_page_evidence_bundles(ds)
    assert len(bundles) == 1
    assert bundles[0]["page"] == 4
    assert "micro_grid_evidence" in bundles[0]
    assert "local_structure_evidence" in bundles[0]


def test_merge_micro_grid_structures_into_bundles():
    ds: dict = {}
    merge_micro_grid_structures_into_bundles(
        ds,
        [{"grid_id": "mg_p4_0", "page": 4, "bbox": [0, 0, 1, 1]}],
    )
    assert ds["_page_evidence_bundles"][0]["page"] == 4
    assert ds["_page_evidence_bundles"][0]["micro_grid_structures"][0]["grid_id"] == "mg_p4_0"


def test_upsert_page_evidence_bundle_stores_region_detect():
    host = type("Host", (), {})()
    upsert_page_evidence_bundle(
        host,
        page=4,
        region_detect={"region_detect_candidates": [{"candidate_id": "c1", "kind": "micro_grid"}]},
    )
    assert host._page_evidence_bundles[0]["region_detect"]["region_detect_candidates"][0]["candidate_id"] == "c1"


def test_build_page_evidence_bundles_ignores_legacy_tracks():
    ds = {
        "_scanned_micro_grid_evidence": [{"page": 5, "lines": []}],
        "_scanned_local_structure_evidence": [{"page": 5, "structures": []}],
    }
    assert build_page_evidence_bundles(ds) == []


def test_bundles_from_legacy_extractor_meta_merges_by_page():
    bundles = bundles_from_legacy_extractor_meta(
        scanned_micro_grid_evidence=[{"page": 4, "page_width": 800, "lines": [], "source": "scanned_page_ocr"}],
        scanned_local_structure_evidence=[
            {
                "page": 4,
                "page_width": 800,
                "structures": [{"structure_id": "ls_p4_0"}],
                "source": "scanned_page_ocr",
            },
        ],
    )
    assert len(bundles) == 1
    assert bundles[0]["page"] == 4
    assert "micro_grid_evidence" in bundles[0]
    assert "local_structure_evidence" in bundles[0]


def test_attach_page_evidence_bundles_preserves_existing():
    ds = domain_specific_with_page_bundles(
        page_evidence_bundle(5, micro_grid_evidence={"page": 5, "lines": []}),
    )
    out = attach_page_evidence_bundles(ds)
    assert out["_page_evidence_bundles"]
    assert "_scanned_micro_grid_evidence" not in out


def test_upsert_page_evidence_bundle_merges_same_page():
    host = type("Host", (), {})()
    upsert_page_evidence_bundle(
        host,
        page=4,
        page_width=800,
        micro_grid_evidence={"page": 4, "lines": [{"content": "a"}]},
    )
    upsert_page_evidence_bundle(
        host,
        page=4,
        local_structure_evidence={"page": 4, "structures": [{"structure_id": "ls_p4_0"}]},
    )
    assert len(host._page_evidence_bundles) == 1
    bundle = host._page_evidence_bundles[0]
    assert bundle["page"] == 4
    assert bundle["micro_grid_evidence"]["lines"]
    assert bundle["local_structure_evidence"]["structures"]


def test_domain_access_ignores_legacy_scanned_tracks_without_bundles():
    ds = {
        "_scanned_micro_grid_evidence": [{"page": 4, "lines": [{"content": "x"}], "tokens": []}],
        "_scanned_local_structure_evidence": [{"page": 4, "structures": [{"structure_id": "ls_p4_0"}]}],
    }
    assert micro_grid_evidence_pages_from_domain_specific(ds) == []
    assert local_structure_evidence_pages_from_domain_specific(ds) == []


def test_micro_grid_evidence_needing_reconstruction_skips_structured_pages():
    ds = domain_specific_with_page_bundles(
        page_evidence_bundle(
            4,
            micro_grid_evidence={"page": 4, "lines": [{"content": "2021", "bbox": [1, 2, 3, 4]}]},
        ),
    )
    assert len(micro_grid_evidence_needing_reconstruction(ds)) == 1

    merge_micro_grid_structures_into_bundles(
        ds,
        [{"grid_id": "mg_p4_0", "page": 4, "bbox": [0, 0, 1, 1]}],
    )
    assert micro_grid_evidence_needing_reconstruction(ds) == []
