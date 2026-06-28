# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Smoke test for the top-level ``perceive_document`` entry point.

Tests that the CPS pipeline can be invoked end-to-end on a small PDF fixture.
This is the outermost ring of the test diamond — it catches regressions in the
entry point wiring, not individual stage logic.
"""

import asyncio
import json
from pathlib import Path

import pytest

from docmirror.input.entry.factory import perceive_document


@pytest.mark.skip(reason="No fixture available in CI; requires sample_1page.pdf")
def test_perceive_document_smoke():
    """Placeholder: Invoke perceive_document on a minimal PDF and verify the result envelope."""
    fixture = Path(__file__).parent.parent / "fixtures" / "sample_1page.pdf"
    if not fixture.exists():
        pytest.skip("Fixture not found: sample_1page.pdf")

    result = asyncio.run(perceive_document(str(fixture)))

    # The result exposes vNext mirror JSON.
    api = result.to_mirror_json_vnext()

    # vNext mirror contract: document-shaped payload, no legacy envelope.
    assert api["mirror"]["schema"] == "docmirror.mirror_json"
    assert "code" not in api
    assert "data" not in api

    # Round-trip through JSON
    roundtrip = json.loads(json.dumps(api))
    assert roundtrip["mirror"]["schema_version"] == api["mirror"]["schema_version"]

    # At least one page was extracted
    pages = api.get("pages") or []
    assert len(pages) >= 1, "Expected at least one extracted page"


@pytest.mark.smoke
def test_perceive_document_entry_point_imports():
    """Verify the perceive_document function import resolves."""
    from docmirror.input.entry.factory import perceive_document as pd
    assert callable(pd)
    assert asyncio.iscoroutinefunction(pd)
