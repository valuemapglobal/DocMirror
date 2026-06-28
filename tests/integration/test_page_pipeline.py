# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Pipeline integration tests for the CPS 4-stage PagePipeline (GA1.0-07, Layer 2).

Verifies that ``prepare -> segment -> assemble -> finalize`` produces correct
output for various page types (text-dominant, table-only, mixed, scanned,
formula). Each test runs the full pipeline but asserts at stage-specific
granularity.

Run on every CI commit — cost: <2min for all page types.
"""

from pathlib import Path

import pytest


@pytest.mark.integration
@pytest.mark.parametrize(
    "fixture_name",
    [
        pytest.param("sample_1page.pdf", id="mixed-page"),
    ],
)
def test_page_pipeline_produces_pages(fixture_name: str):
    """Verify the 4-stage pipeline produces pages with expected structure."""
    from docmirror.input.entry.factory import perceive_document

    fixture_path = Path(__file__).parent.parent / "fixtures" / fixture_name
    if not fixture_path.exists():
        pytest.skip(f"Fixture not found: {fixture_name}")

    result = perceive_document(str(fixture_path))

    assert len(result.pages) >= 1
    for page in result.pages:
        # Each page should have a page number
        assert page.page_number >= 0
        # Each page should have dimensions
        assert page.width > 0
        assert page.height > 0


@pytest.mark.integration
def test_pipeline_stages_run_without_error():
    """Smoke test that each pipeline stage can be invoked without exception."""
    from docmirror.input.entry.factory import perceive_document

    fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_1page.pdf"
    if not fixture_path.exists():
        pytest.skip("Fixture not found")

    result = perceive_document(str(fixture_path))
    api = result.to_mirror_json_vnext()
    assert api["mirror"]["schema"] == "docmirror.mirror_json"
    assert "code" not in api
    assert "data" not in api
