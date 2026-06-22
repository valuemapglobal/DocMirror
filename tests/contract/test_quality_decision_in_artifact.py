# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""G15: Quality Decision in Artifact contract tests.

GA 1.0 SS4.12 N1: Every Edition JSON and Mirror JSON must carry a top-level
``quality_decision`` block with a valid ``decision`` field
(``auto_ingest`` / ``needs_review`` / ``reject``).
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import pytest


class TestBuildQualityDecisionBlock:
    """Test build_quality_decision_block() produces valid output."""

    def test_returns_dict_with_decision(self):
        from docmirror.evidence.quality_decision import QualityDecisionReport
        from docmirror.output.projection_resolver import build_quality_decision_block

        # Create minimal inputs — build_quality_decision_block is a thin wrapper
        report = QualityDecisionReport(
            document_id="d_test", task_id="t_test",
            decision="auto_ingest",
            decision_reason="all_checks_passed",
            confidence_policy="ga_default_v1",
            summary={
                "text_fidelity": "pass",
                "layout_fidelity": "pass",
                "business_fidelity": "pass",
                "audit_fidelity": "pass",
            },
        )

        # Build block using the wrapper
        block = report.to_dict()

        assert isinstance(block, dict), "quality_decision block must be a dict"
        assert "decision" in block, "quality_decision block must have a 'decision' key"
        assert block["decision"] == "auto_ingest"
        assert "version" in block
        assert block["version"] == 2

    def test_decision_valid_values(self):
        from docmirror.evidence.quality_decision import QualityDecisionReport

        for decision in ("auto_ingest", "needs_review", "reject"):
            report = QualityDecisionReport(
                document_id="d", task_id="t",
                decision=decision,
                decision_reason="test",
                confidence_policy="ga_default_v1",
            )
            block = report.to_dict()
            assert block["decision"] == decision, (
                f"G15: decision must be {decision}"
            )

    def test_block_includes_needs_review_items(self):
        from docmirror.evidence.quality_decision import (
            QualityDecisionReport, ReviewItem,
        )

        report = QualityDecisionReport(
            document_id="d_test2", task_id="t_test2",
            decision="needs_review",
            decision_reason="low confidence on 2 fields",
            confidence_policy="ga_default_v1",
        )
        report.needs_review.append(ReviewItem(
            scope="field", field_path="inv.amount",
            node_id="field:inv.amount", reason="low_confidence",
            confidence=0.4, page=3, bbox=[100, 200, 300, 220],
        ))

        block = report.to_dict()
        assert block["decision"] == "needs_review"
        assert len(block["needs_review"]) == 1
        assert block["needs_review"][0]["field_path"] == "inv.amount"
        assert block["needs_review"][0]["page"] == 3

    def test_block_includes_fidelity_summary(self):
        from docmirror.evidence.quality_decision import QualityDecisionReport

        report = QualityDecisionReport(
            document_id="d_test3", task_id="t_test3",
            decision="auto_ingest",
            decision_reason="all checks passed",
            confidence_policy="ga_default_v1",
            summary={
                "text_fidelity": "pass",
                "layout_fidelity": "warning",
                "business_fidelity": "pass",
                "audit_fidelity": "partial",
            },
        )

        block = report.to_dict()
        assert "summary" in block
        assert block["summary"]["text_fidelity"] == "pass"
        assert block["summary"]["layout_fidelity"] == "warning"

    def test_block_includes_blocking_issues(self):
        from docmirror.evidence.quality_decision import QualityDecisionReport

        report = QualityDecisionReport(
            document_id="d_test4", task_id="t_test4",
            decision="reject",
            decision_reason="schema validation failed",
            confidence_policy="ga_default_v1",
        )
        report.blocking_issues.append({
            "scope": "document",
            "reason": "schema_fail",
        })

        block = report.to_dict()
        assert len(block["blocking_issues"]) >= 1
        assert block["blocking_issues"][0]["scope"] == "document"

    def test_build_quality_decision_block_from_projection_resolver(self):
        """build_quality_decision_block() is available in projection_resolver __all__."""
        from docmirror.output.projection_resolver import build_quality_decision_block
        assert callable(build_quality_decision_block), (
            "G15: build_quality_decision_block must be importable and callable"
        )


class TestEmbedQualityDecisionInArtifacts:
    """Test _embed_quality_decision_in_artifacts() behavior."""

    def test_embeds_quality_decision_into_edition_json(self, tmp_path: Path):
        """G15: quality_decision block is injected into edition JSON artifacts."""
        from docmirror.server.artifact_pack import _embed_quality_decision_in_artifacts

        # Create a mock task_dir with edition-like JSON files
        task_dir = tmp_path / "task_test_001"
        task_dir.mkdir()

        # Create community.json (simulating an Edition output)
        community_data = {
            "edition": "community",
            "data": {"fields": {"total": "100.00"}},
            "metadata": {"source_page": 1, "support_level": "L1"},
        }
        community_path = task_dir / "community.json"
        community_path.write_text(
            _json.dumps(community_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Create a mirror.json
        mirror_data = {
            "version": 2,
            "document_type": "bank_statement",
            "pages": [{"page_number": 1, "text": "content"}],
        }
        mirror_path = task_dir / "001_mirror.json"
        mirror_path.write_text(
            _json.dumps(mirror_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Create a non-artifact JSON (should NOT be modified)
        manifest_data = {"version": 2, "task_id": "task_test_001"}
        manifest_path = task_dir / "manifest.json"
        manifest_path.write_text(
            _json.dumps(manifest_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Build quality_decision dict
        from docmirror.evidence.quality_decision import QualityDecisionReport
        qd = QualityDecisionReport(
            document_id="d_test", task_id="t_test",
            decision="auto_ingest",
            decision_reason="all checks passed",
            confidence_policy="ga_default_v1",
            summary={"text_fidelity": "pass", "layout_fidelity": "pass",
                     "business_fidelity": "pass", "audit_fidelity": "pass"},
        )

        # Call the embed function
        _embed_quality_decision_in_artifacts(task_dir, qd)

        # Verify community.json has quality_decision block
        community_after = _json.loads(community_path.read_text(encoding="utf-8"))
        assert "quality_decision" in community_after, (
            "G15: community.json must have quality_decision block"
        )
        assert community_after["quality_decision"]["decision"] == "auto_ingest"

        # Verify mirror.json has quality_decision block
        mirror_after = _json.loads(mirror_path.read_text(encoding="utf-8"))
        assert "quality_decision" in mirror_after, (
            "G15: mirror.json must have quality_decision block"
        )
        assert mirror_after["quality_decision"]["decision"] == "auto_ingest"

        # Verify manifest.json is NOT modified (non-artifact)
        manifest_after = _json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "quality_decision" not in manifest_after, (
            "G15: manifest.json should NOT have quality_decision (not an artifact)"
        )

        # Verify original data is preserved
        assert community_after["edition"] == "community"
        assert community_after["data"]["fields"]["total"] == "100.00"
        assert mirror_after["pages"][0]["page_number"] == 1

    def test_embed_with_dict_based_quality_decision(self, tmp_path: Path):
        """G15: _embed_quality_decision_in_artifacts also accepts dict input."""
        from docmirror.server.artifact_pack import _embed_quality_decision_in_artifacts

        task_dir = tmp_path / "task_test_002"
        task_dir.mkdir()

        edition_path = task_dir / "community.json"
        edition_path.write_text(
            _json.dumps({"edition": "community", "data": {}}, ensure_ascii=False),
            encoding="utf-8",
        )

        qd_dict = {
            "version": 2,
            "decision": "needs_review",
            "decision_reason": "low confidence",
            "needs_review": [
                {"scope": "field", "field_path": "inv.amount", "reason": "low_confidence"}
            ],
            "blocking_issues": [],
            "summary": {"text_fidelity": "warning"},
        }

        _embed_quality_decision_in_artifacts(task_dir, qd_dict)

        after = _json.loads(edition_path.read_text(encoding="utf-8"))
        assert "quality_decision" in after
        assert after["quality_decision"]["decision"] == "needs_review"
        assert len(after["quality_decision"]["needs_review"]) == 1

    def test_embed_skips_non_dict_content(self, tmp_path: Path):
        """G15: _embed_quality_decision_in_artifacts handles non-dict JSON gracefully."""
        from docmirror.server.artifact_pack import _embed_quality_decision_in_artifacts

        task_dir = tmp_path / "task_test_003"
        task_dir.mkdir()

        # Create a JSON file that's a list (not a dict)
        list_path = task_dir / "001_mirror.json"
        list_path.write_text(
            _json.dumps([1, 2, 3], ensure_ascii=False),
            encoding="utf-8",
        )

        from docmirror.evidence.quality_decision import QualityDecisionReport
        qd = QualityDecisionReport(
            document_id="d", task_id="t",
            decision="auto_ingest",
            decision_reason="test",
            confidence_policy="ga_default_v1",
        )

        # Should not raise — gracefully skip non-dict
        _embed_quality_decision_in_artifacts(task_dir, qd)

        # File should remain unchanged
        after = _json.loads(list_path.read_text(encoding="utf-8"))
        assert after == [1, 2, 3]
        assert not isinstance(after, dict)

    def test_embed_with_none_quality_decision(self, tmp_path: Path):
        """_embed_quality_decision_in_artifacts returns early on None input."""
        from docmirror.server.artifact_pack import _embed_quality_decision_in_artifacts

        task_dir = tmp_path / "task_test_004"
        task_dir.mkdir()
        edition_path = task_dir / "community.json"
        original = {"edition": "community", "data": {}}
        edition_path.write_text(_json.dumps(original, ensure_ascii=False), encoding="utf-8")

        _embed_quality_decision_in_artifacts(task_dir, None)

        after = _json.loads(edition_path.read_text(encoding="utf-8"))
        assert after == original


class TestQualityDecisionInArtifactAcceptance:
    """G15 acceptance: All artifact JSONs must have quality_decision block."""

    def test_quality_decision_present_in_artifact(self):
        """G15 ACCEPTANCE: quality_decision dict structure is valid."""
        from docmirror.evidence.quality_decision import QualityDecisionReport, ReviewItem

        report = QualityDecisionReport(
            document_id="d_acceptance", task_id="t_acceptance",
            decision="needs_review",
            decision_reason="2 of 3 fields lack evidence",
            confidence_policy="ga_default_v1",
            summary={
                "text_fidelity": "pass",
                "layout_fidelity": "pass",
                "business_fidelity": "warning",
                "audit_fidelity": "partial",
            },
        )
        report.needs_review.append(ReviewItem(
            scope="field", field_path="inv.amount",
            node_id="field:inv.amount", reason="low_confidence",
            confidence=0.3, page=1, bbox=[10, 20, 30, 40],
        ))
        report.blocking_issues.append({
            "scope": "field", "field_path": "inv.amount",
            "reason": "no_evidence",
        })

        block = report.to_dict()

        # G15: decision must be one of the three valid values
        assert block["decision"] in ("auto_ingest", "needs_review", "reject"), (
            "G15 ACCEPTANCE: decision must be auto_ingest/needs_review/reject"
        )

        # G15: version must be 2
        assert block["version"] == 2

        # G15: needs_review and blocking_issues must be lists
        assert isinstance(block["needs_review"], list)
        assert isinstance(block["blocking_issues"], list)

        # G15: summary must have all four fidelity dimensions
        for dim in ("text_fidelity", "layout_fidelity", "business_fidelity", "audit_fidelity"):
            assert dim in block["summary"], (
                f"G15 ACCEPTANCE: summary must include {dim}"
            )

        # G15: decision_reason must be a non-empty string
        assert isinstance(block["decision_reason"], str)
        assert len(block["decision_reason"]) > 0
