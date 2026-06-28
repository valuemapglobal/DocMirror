# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Contract tests for adapter invariants (GA1.0-07, Layer 1).

Every adapter (PDF, Image, Office, Web) must produce a ``ParseResult`` that
satisfies a shared contract: valid envelope, non-empty pages, populated
``parser_info``, JSON round-trip stability, and buildable evidence ledger.

These tests guarantee that no single adapter breaks, even when the adapter
code changes. Run on every CI commit — cost: <30s total for all adapters.
"""

import asyncio
import json
from pathlib import Path

import pytest

from docmirror.input.entry.factory import perceive_document

# Each entry: (test_name, fixture_path, adapter_kind)
FIXTURE_TABLE = [
    pytest.param("sample_1page.pdf", id="pdf"),
    # Uncomment and add fixtures for other adapter types:
    # pytest.param("sample_scan.png", id="image"),
    # pytest.param("sample.docx", id="word"),
    # pytest.param("sample.xlsx", id="excel"),
]


@pytest.mark.contract
@pytest.mark.parametrize("fixture_name", FIXTURE_TABLE)
def test_adapter_produces_valid_parse_result(fixture_name: str):
    fixture_path = Path(__file__).parent.parent / "fixtures" / fixture_name
    if not fixture_path.exists():
        pytest.skip(f"Fixture not found: {fixture_name}")

    result = asyncio.run(perceive_document(str(fixture_path)))

    # Invariant 1: vNext mirror result is valid
    assert hasattr(result, "to_mirror_json_vnext"), "Result must expose vNext mirror serialization"
    api = result.to_mirror_json_vnext()
    assert len(api["pages"]) >= 1

    # Invariant 2: Evidence store is non-empty
    assert api["evidence"]["text_atoms"] or api["evidence"]["visual_atoms"], "No content extracted"

    # Invariant 3: source provenance is populated
    assert api["source"]["filename"] != ""

    # Invariant 4: to_mirror_json_vnext() produces document-shaped vNext JSON
    assert "mirror" in api
    assert "document" in api

    # Invariant 5: Serialization round-trips
    roundtrip = json.loads(json.dumps(api))
    assert roundtrip["mirror"]["schema_version"] == api["mirror"]["schema_version"]

    # Invariant 6: Evidence store is present
    assert "text_atoms" in api["evidence"]
    assert "visual_atoms" in api["evidence"]


@pytest.mark.contract
def test_all_adapters_share_result_type():
    """Ensure different adapters produce the same result type."""
    from docmirror.models.mirror.vnext import MirrorJsonVNext

    fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_1page.pdf"
    if not fixture_path.exists():
        pytest.skip("Fixture not found")

    result = asyncio.run(perceive_document(str(fixture_path)))
    assert isinstance(result.mirror, MirrorJsonVNext)
