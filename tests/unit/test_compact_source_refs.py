# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for compact edition source-ref metadata."""

from __future__ import annotations

from docmirror.plugins._base.mirror_source_refs import (
    compact_projection_lineage_source_refs,
    compact_source_ref_metadata,
    embed_full_source_refs,
)


def test_embed_full_source_refs_only_for_ga_profiles():
    assert embed_full_source_refs("standard") is False
    assert embed_full_source_refs("minimal") is False
    assert embed_full_source_refs("full") is True
    assert embed_full_source_refs("forensic") is True


def test_compact_source_ref_metadata_replaces_lists_with_counts():
    meta = {
        "source_fact_ids": ["cell:p1:t0:r0:c0", "cell:p1:t0:r0:c1"],
        "evidence_ids": ["ev:cell:p1:t0:r0:c0", "ev:cell:p1:t0:r0:c1"],
        "parser": "docmirror-community",
    }
    compact_source_ref_metadata(meta, mirror_ref="001_mirror.json")

    assert "source_fact_ids" not in meta
    assert "evidence_ids" not in meta
    assert meta["source_fact_id_count"] == 2
    assert meta["evidence_id_count"] == 2
    assert meta["source_facts_ref"] == "001_mirror.json"


def test_compact_projection_lineage_source_refs():
    lineage = {
        "edition_lineage": {
            "projection_id": "proj:community.edition",
            "source_fact_ids": ["cell:p1:t0:r0:c0"],
            "evidence_ids": ["ev:cell:p1:t0:r0:c0"],
        }
    }
    compact_projection_lineage_source_refs(lineage, mirror_ref="001_mirror.json")

    el = lineage["edition_lineage"]
    assert "source_fact_ids" not in el
    assert el["source_fact_id_count"] == 1
    assert el["source_facts_ref"] == "001_mirror.json"
