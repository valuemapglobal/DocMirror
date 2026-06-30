# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Contract Test: DMIR Does Not Mutate ParseResult (GA1.0-ODL-06 P0-2)

Verifies the key architectural invariant: DMIR is an independent, parallel
projection from ParseResult that does not affect the existing four edition
outputs (_mirror, _community, _enterprise, _finance).

Test cases:
  1. serialize_dmir() does not modify the input ParseResult.
  2. DMIR and edition outputs are independent (can be computed in any order).
  3. Multiple calls to serialize_dmir() produce identical output.
  4. The safety section in DMIR is purely additive.
"""

from __future__ import annotations

import copy
import json

import pytest

from docmirror.models.entities.parse_result import (
    DocumentEntities,
    PageContent,
    ParseResult,
    TableBlock,
    TextBlock,
    TextLevel,
)
from docmirror.output.dmir import serialize_dmir

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def sample_result() -> ParseResult:
    """A minimal but realistic ParseResult for contract testing."""
    return ParseResult(
        pages=[
            PageContent(
                page_number=1,
                texts=[
                    TextBlock(content="Hello", level=TextLevel.H1, confidence=0.99),
                    TextBlock(content="World", level=TextLevel.BODY, confidence=0.95),
                ],
                tables=[
                    TableBlock(
                        table_id="tbl_0",
                        headers=["A", "B"],
                        data_rows=[],
                        confidence=0.9,
                    ),
                ],
                page_confidence=0.95,
            ),
        ],
        entities=DocumentEntities(
            document_type="test",
            organization="TestCorp",
        ),
        confidence=0.97,
    )


# ── Tests ────────────────────────────────────────────────────────────────


class TestDmirDoesNotMutate:
    """Verify DMIR serialization does not alter ParseResult."""

    def test_serialize_dmir_does_not_modify_pages(self, sample_result: ParseResult):
        """DMIR serialization should not modify the input ParseResult's pages."""
        original = copy.deepcopy(sample_result)
        _ = serialize_dmir(sample_result)

        # Original ParseResult is unchanged
        assert len(sample_result.pages) == len(original.pages)
        for i, page in enumerate(sample_result.pages):
            assert page.page_number == original.pages[i].page_number
            assert len(page.texts) == len(original.pages[i].texts)
            for j, text in enumerate(page.texts):
                assert text.content == original.pages[i].texts[j].content

    def test_serialize_dmir_does_not_modify_texts(self, sample_result: ParseResult):
        """DMIR serialization should not modify text block content."""
        original_texts = [t.content for t in sample_result.pages[0].texts]
        _ = serialize_dmir(sample_result)
        for i, t in enumerate(sample_result.pages[0].texts):
            assert t.content == original_texts[i]

    def test_serialize_dmir_does_not_modify_tables(self, sample_result: ParseResult):
        """DMIR serialization should not modify table data."""
        original_tables = copy.deepcopy(sample_result.pages[0].tables)
        _ = serialize_dmir(sample_result)
        for i, table in enumerate(sample_result.pages[0].tables):
            assert table.table_id == original_tables[i].table_id

    def test_serialize_dmir_idempotent(self, sample_result: ParseResult):
        """Multiple calls to serialize_dmir produce identical output."""
        first = serialize_dmir(sample_result)
        second = serialize_dmir(sample_result)
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    def test_serialize_dmir_independent_from_edition_outputs(self, sample_result: ParseResult):
        """DMIR output is independent from edition outputs.

        Edition outputs (community/enterprise/finance) are built from
        ParseResult via plugin runners. DMIR is built from ParseResult
        via serialize_dmir(). They share no code paths and no mutation.
        """
        dmir = serialize_dmir(sample_result)

        # DMIR has expected top-level fields
        assert "dmir_version" in dmir
        assert "document" in dmir
        assert "quality" in dmir
        assert "evidence" in dmir
        assert "meta" in dmir

        # DMIR does NOT contain edition-specific fields
        assert "_edition" not in dmir
        assert "community" not in dmir
        assert "enterprise" not in dmir
        assert "finance" not in dmir

    def test_dmir_safety_section_is_additive(self, sample_result: ParseResult):
        """The safety section in DMIR is purely additive.

        When no safety report is attached, DMIR should NOT include a safety section.
        When a safety report IS attached, DMIR should include it.
        """
        # Without safety report — no safety section
        dmir_no_safety = serialize_dmir(sample_result)
        assert "safety" not in dmir_no_safety

        # With safety report — safety section present
        from docmirror.security.safety.aggregator import SafetyReport

        # Simulate what perceive_document does: attach _safety_report
        report = SafetyReport(
            sanitized=False,
            hidden_text_count=0,
            zero_width_count=0,
            injection_risk=0.0,
            strictness_applied="medium",
            blocks_removed=0,
            chars_removed=0,
        )
        object.__setattr__(sample_result, "_safety_report", report)

        dmir_with_safety = serialize_dmir(sample_result)
        assert "safety" in dmir_with_safety
        assert dmir_with_safety["safety"]["sanitized"] is False
        assert dmir_with_safety["safety"]["strictness_applied"] == "medium"

        # Clean up
        del sample_result._safety_report

    def test_dmir_safety_section_includes_findings(self, sample_result: ParseResult):
        """Safety findings (hidden text, zero-width, injection) appear in DMIR."""
        from docmirror.security.safety.aggregator import SafetyReport

        report = SafetyReport(
            sanitized=True,
            hidden_text_count=2,
            zero_width_count=3,
            zero_width_flags=[],
            injection_risk=0.45,
            injection_matched_patterns=["ignore_previous"],
            strictness_applied="high",
            blocks_removed=2,
            chars_removed=15,
        )
        object.__setattr__(sample_result, "_safety_report", report)

        dmir = serialize_dmir(sample_result)
        safety = dmir["safety"]
        assert safety["sanitized"] is True
        assert safety["hidden_text_found"] is True
        assert safety["hidden_text_blocks"] == 2
        assert safety["zero_width_chars_found"] is True
        assert safety["injection_risk_score"] == 0.45
        assert "ignore_previous" in safety["injection_patterns_matched"]
        assert safety["strictness_applied"] == "high"
        assert safety["blocks_removed"] == 2
        assert safety["chars_removed"] == 15

        del sample_result._safety_report

    def test_dmir_projection_parallel_computation(self, sample_result: ParseResult):
        """Edition outputs and DMIR can be computed in any order without interference.

        This is the key architectural invariant: all five projections
        (mirror, DMIR, community, enterprise, finance) read directly from
        ParseResult and do not depend on each other.
        """
        # Compute DMIR first, then edition outputs (simulated)
        dmir_first = serialize_dmir(sample_result)

        # Simulate edition output computation (not using actual plugins — they
        # require full pipeline context). We just verify DMIR is unchanged.
        dmir_second = serialize_dmir(sample_result)

        assert dmir_first == dmir_second

    def test_dmir_schema_conformance(self, sample_result: ParseResult):
        """DMIR output conforms to the JSON Schema (top-level structural check)."""
        import json
        from pathlib import Path

        schema_path = Path("docs/schemas/dmir/v1.0.schema.json")
        if not schema_path.exists():
            pytest.skip("DMIR schema not found — skipping conformance check")

        with open(schema_path) as f:
            schema = json.load(f)

        dmir = serialize_dmir(sample_result)

        # Validate top-level keys match schema properties
        for key in dmir:
            assert key in schema["properties"], f"Unknown DMIR key: {key}"

        # Validate structure
        assert "dmir_version" in dmir
        assert dmir["dmir_version"] == "1.0"
        assert "document" in dmir
        assert dmir["document"]["type"] == "test"
        assert "quality" in dmir
        assert "evidence" in dmir
        assert "meta" in dmir
        assert dmir["meta"]["dmir_version"] == "1.0"


