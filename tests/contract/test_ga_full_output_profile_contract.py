# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""GA Full Output Profile contract test — GA 1.0 design OUT0-5.

Validates that a single ``ga_full``-style output run (or its functional equivalent
via ``write_four_files`` + ``ensure_quickstart_artifact_pack``) produces the
complete artifact pack: Mirror, Markdown, Editions, Evidence Bundle, Quality Report,
Visual Debug, and Manifest with artifact_roles and schema_versions.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from docmirror.configs.output_profile import GA_FULL, resolve_profile
from docmirror.evidence.bundle import build_evidence_bundle
from docmirror.models.entities.parse_result import (
    CellValue,
    DocumentEntities,
    PageContent,
    ParseResult,
    TableBlock,
    TableRow,
)
from docmirror.server.artifact_pack import ensure_quickstart_artifact_pack
from docmirror.server.edition_outputs import write_four_files
from docmirror.server.output_builder import build_all_projections


def _make_minimal_result(document_type: str = "bank_statement") -> ParseResult:
    result = ParseResult(
        status="success",
        pages=[
            PageContent(
                page_number=1,
                tables=[
                    TableBlock(
                        table_id="t1",
                        headers=["Name", "Amount", "Date"],
                        rows=[
                            TableRow(
                                cells=[
                                    CellValue(text="Alice", bbox=[10, 10, 50, 20], confidence=0.95),
                                    CellValue(text="100.00", bbox=[60, 10, 100, 20], confidence=0.92),
                                    CellValue(text="2024-01-15", bbox=[110, 10, 160, 20], confidence=0.97),
                                ]
                            ),
                            TableRow(
                                cells=[
                                    CellValue(text="Bob", bbox=[10, 25, 50, 35], confidence=0.88),
                                    CellValue(text="200.00", bbox=[60, 25, 100, 35], confidence=0.97),
                                    CellValue(text="2024-01-16", bbox=[110, 25, 160, 35], confidence=0.93),
                                ]
                            ),
                        ],
                    )
                ],
            )
        ],
    )
    result.entities = DocumentEntities(document_type=document_type)
    return result


def test_ga_full_profile_is_defined():
    profile = resolve_profile("ga_full")
    assert profile.name == "ga_full"
    assert profile.mirror is True
    assert profile.community is True
    assert profile.evidence_bundle is True
    assert profile.quality_report is True
    assert profile.visual_debug is True
    assert profile.manifest is True
    assert profile.markdown is True


def test_legacy_json_profile_is_defined():
    profile = resolve_profile("legacy_json")
    assert profile.name == "legacy_json"
    assert profile.mirror is True
    assert profile.markdown is False
    assert profile.evidence_bundle is False


def test_all_profiles_listed():
    from docmirror.configs.output_profile import list_profiles
    names = list_profiles()
    for required in ("ga_full", "legacy_json", "quickstart"):
        assert required in names, f"missing profile: {required}"


def test_ga_full_produces_mirror_and_editions():
    result = _make_minimal_result()
    projections = build_all_projections(
        result,
        full_text="",
        file_path="test.pdf",
        mirror_level="standard",
        include_text=False,
        request_id="ga_full_test",
        editions=("community", "enterprise", "finance"),
    )
    assert "mirror" in projections, "mirror projection should always be present"
    assert "community" in projections, "community projection should always be present"


def test_ga_full_writes_artifact_pack():
    result = _make_minimal_result()
    with TemporaryDirectory() as tmpdir:
        task_dir = Path(tmpdir) / "ga_full_test"
        task_dir.mkdir(parents=True, exist_ok=True)

        task_id, written = write_four_files(
            result,
            output_dir=task_dir.parent,
            file_path="test_bank.pdf",
            editions=("mirror", "community"),
            file_id="001",
            task_id="ga_full_test_task",
            overwrite=True,
        )

        actual_dir = task_dir.parent / task_id
        assert actual_dir.is_dir(), f"task dir not created at {actual_dir}"

        artifacts = sorted(f.name for f in actual_dir.iterdir() if f.is_file())
        assert "001_mirror.json" in artifacts, f"missing mirror.json in {artifacts}"
        assert "001_community.json" in artifacts, f"missing community.json in {artifacts}"
        assert "005_evidence_bundle.json" in artifacts, f"missing evidence bundle in {artifacts}"
        assert "output.md" in artifacts, f"missing output.md in {artifacts}"
        assert "quality_report.json" in artifacts, f"missing quality_report.json in {artifacts}"
        assert "visual_debug.html" in artifacts, f"missing visual_debug.html in {artifacts}"
        assert "manifest.json" in artifacts, f"missing manifest.json in {artifacts}"


def test_manifest_has_artifact_roles_and_schema_versions():
    result = _make_minimal_result()
    with TemporaryDirectory() as tmpdir:
        task_dir = Path(tmpdir) / "test_manifest"
        task_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "version": 1,
            "task_id": "t1",
            "document_id": "d1",
            "file_id": "001",
            "input": {"file_path": "test.pdf"},
            "artifacts": {
                "mirror": "001_mirror.json",
                "community": "001_community.json",
                "evidence": "005_evidence_bundle.json",
            },
        }
        updated = ensure_quickstart_artifact_pack(task_dir, manifest, result=result, profile=GA_FULL)

        assert updated["output_profile"] == "ga_full"
        assert "schema_versions" in updated
        sv = updated["schema_versions"]
        for key in ("mirror", "community", "evidence_bundle", "manifest"):
            assert key in sv, f"schema_versions missing key: {key}"
        roles = updated.get("artifact_roles", {})
        assert isinstance(roles, dict)
        for role in ("mirror", "markdown", "evidence_bundle", "quality_report"):
            assert role in roles, f"artifact_roles missing: {role}"


def test_quality_report_has_three_consumer_readiness():
    result = _make_minimal_result()
    with TemporaryDirectory() as tmpdir:
        task_dir = Path(tmpdir) / "test_qr"
        task_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "version": 1,
            "task_id": "t1",
            "document_id": "d1",
            "file_id": "001",
            "input": {"file_path": "test.pdf"},
            "artifacts": {},
        }
        ensure_quickstart_artifact_pack(task_dir, manifest, result=result, profile=GA_FULL)
        qr_path = task_dir / "quality_report.json"
        assert qr_path.exists()
        import json
        qr = json.loads(qr_path.read_text(encoding="utf-8"))
        readiness = qr.get("readiness", {})
        for consumer in ("human_readable", "system_readable", "audit_readable"):
            # readiness keys are human_readable_markdown, system_readable_edition, audit_readable_evidence
            found = any(k.startswith(consumer) for k in readiness)
            assert found, f"readiness missing key starting with: {consumer}"


def test_evidence_bundle_v2_written_for_ga_full():
    result = _make_minimal_result()
    bundle = build_evidence_bundle(result, task_id="t1", document_id="d1", file_id="001")
    assert bundle["version"] == 2, f"expected v2 bundle, got v{bundle['version']}"
    assert "ledger" in bundle
    assert "projection_evidence" in bundle
    assert "field_evidence" in bundle
    assert "unresolved" in bundle
    assert "support" in bundle
    assert "redaction_safe" in bundle.get("support", {})


def test_fact_ids_stable_in_mirror():
    result1 = _make_minimal_result()
    result2 = _make_minimal_result()
    from docmirror.models.mirror.fact_identity import collect_mirror_fact_ids
    ids1 = collect_mirror_fact_ids(result1)
    ids2 = collect_mirror_fact_ids(result2)
    assert ids1 == ids2, "fact_ids should be deterministic"
    assert len(ids1["page"]) == 1
    assert ids1["page"][0] == "page:1"
    assert len(ids1["table"]) == 1
    assert ids1["table"][0] == "table:p1:t0"
    assert len(ids1["cell"]) == 6


def test_visual_debug_html_generated():
    result = _make_minimal_result()
    with TemporaryDirectory() as tmpdir:
        task_dir = Path(tmpdir) / "test_vd"
        task_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "version": 1,
            "task_id": "t1",
            "document_id": "d1",
            "file_id": "001",
            "input": {"file_path": "test.pdf"},
            "artifacts": {},
        }
        ensure_quickstart_artifact_pack(task_dir, manifest, result=result, profile=GA_FULL)
        vd_path = task_dir / "visual_debug.html"
        assert vd_path.exists()
        html = vd_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in html or "<html" in html
        assert "needs_review" in html or "Needs Review" in html or "filter" in html.lower()
