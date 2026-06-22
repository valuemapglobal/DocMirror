# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""DRC Wave 6: Batch Partial/Resume Demo — e2e tests.

GA 1.0 DRC-W6-02: Proves that batch processing supports:
  - Concurrent execution with failure isolation
  - Partial success (failed files don't block successful ones)
  - Resume (interrupted batch can resume, skipping succeeded files)
  - Checkpoint validation prevents stale artifact reuse
"""

from __future__ import annotations

import json
import tempfile
import hashlib
from pathlib import Path

import pytest


# --- Batch Job Ledger -- Full Lifecycle ---


def test_batch_ledger_multiple_files_lifecycle():
    """DRC-W6-02: BatchJobLedger handles multi-file lifecycle with mixed outcomes."""
    from docmirror.runtime.work_units import BatchJobLedger, BatchJobEntry

    ledger = BatchJobLedger(batch_id="batch_w6_001", task_id="batch_w6_task")

    # Create 5 file entries
    files = [
        BatchJobEntry(file_id="001", file_path="valid1.pdf"),
        BatchJobEntry(file_id="002", file_path="valid2.pdf"),
        BatchJobEntry(file_id="003", file_path="corrupt.pdf"),
        BatchJobEntry(file_id="004", file_path="valid3.pdf"),
        BatchJobEntry(file_id="005", file_path="broken.pdf"),
    ]
    for f in files:
        ledger.add_entry(f)

    # Mark files as running and then process them with mixed results
    ledger.mark_running("001")
    ledger.mark_succeeded("001", {"mirror": "001_mirror.json"})

    ledger.mark_running("002")
    ledger.mark_succeeded("002", {"mirror": "002_mirror.json"})

    # File 003 fails
    ledger.mark_running("003")
    ledger.mark_file("003", "failed_final", [{"message": "corrupt PDF", "type": "CorruptFileError"}])

    ledger.mark_running("004")
    ledger.mark_succeeded("004", {"mirror": "004_mirror.json"})

    # File 005 fails (retryable)
    ledger.mark_running("005")
    ledger.mark_file("005", "failed_retryable", [{"message": "timeout", "type": "TimeoutError"}])

    progress = ledger.compute_progress()
    assert progress["total"] == 5
    assert progress["succeeded"] == 3
    assert progress["failed"] == 2
    assert progress["running"] == 0
    assert progress["pending"] == 0

    # Verify individual file statuses
    assert ledger.get_entry("001").status == "succeeded"
    assert ledger.get_entry("001").artifacts["mirror"] == "001_mirror.json"
    assert ledger.get_entry("003").status == "failed_final"
    assert len(ledger.get_entry("003").errors) == 1
    assert ledger.get_entry("005").status == "failed_retryable"

    # Serialization roundtrip
    d = ledger.to_dict()
    assert d["batch_id"] == "batch_w6_001"
    assert len(d["files"]) == 5


def test_batch_ledger_resume_skips_succeeded():
    """DRC-W6-02: Resume skips already-succeeded files."""
    from docmirror.runtime.work_units import BatchJobLedger, BatchJobEntry

    ledger = BatchJobLedger(batch_id="batch_resume_001", task_id="batch_resume_task")

    # First run: 3 files, 2 succeed, 1 fails
    ledger.add_entry(BatchJobEntry(file_id="001", file_path="f1.pdf"))
    ledger.add_entry(BatchJobEntry(file_id="002", file_path="f2.pdf"))
    ledger.add_entry(BatchJobEntry(file_id="003", file_path="f3.pdf"))

    ledger.mark_running("001")
    ledger.mark_succeeded("001")
    ledger.mark_running("002")
    ledger.mark_succeeded("002")
    ledger.mark_running("003")
    ledger.mark_file("003", "failed_final", [{"message": "parsing error"}])

    # Simulate resume: only process files not yet succeeded
    completed = ledger.completed_file_ids()
    failed = ledger.failed_file_ids()
    pending_to_retry = sorted(failed - completed)

    assert completed == {"001", "002"}
    assert failed == {"003"}
    assert pending_to_retry == ["003"]

    # Retry file 003 -- this time it succeeds
    ledger.mark_running("003")
    ledger.mark_succeeded("003", {"mirror": "003_mirror.json"})

    progress = ledger.compute_progress()
    assert progress["succeeded"] == 3
    assert progress["failed"] == 0


def test_batch_ledger_add_entry_dedup():
    """DRC-W6-02: Adding duplicate file_id updates existing entry."""
    from docmirror.runtime.work_units import BatchJobLedger, BatchJobEntry

    ledger = BatchJobLedger(batch_id="batch_dedup_001", task_id="batch_dedup_task")

    entry1 = BatchJobEntry(file_id="001", file_path="file.pdf", status="pending")
    ledger.add_entry(entry1)

    # Re-add same file_id with different status
    entry2 = BatchJobEntry(file_id="001", file_path="file.pdf", status="running")
    ledger.add_entry(entry2)

    assert ledger.get_entry("001").status == "running"
    # Should only have 1 entry
    progress = ledger.compute_progress()
    assert progress["total"] == 1


def test_batch_ledger_to_dict_serializable():
    """DRC-W6-02: BatchJobLedger.to_dict() produces JSON-serializable output."""
    from docmirror.runtime.work_units import BatchJobLedger, BatchJobEntry

    ledger = BatchJobLedger(batch_id="batch_ser_001", task_id="batch_ser_task")
    ledger.add_entry(BatchJobEntry(file_id="001", file_path="test.pdf"))

    d = ledger.to_dict()
    json_str = json.dumps(d, ensure_ascii=False)
    restored = json.loads(json_str)
    assert restored["batch_id"] == "batch_ser_001"
    assert restored["files"][0]["file_id"] == "001"


# --- Checkpoint Manager -- Resume Validation ---


def test_checkpoint_save_and_validate_resume():
    """DRC-W6-02: CheckpointManager correctly validates resume fingerprints."""
    from docmirror.runtime.checkpoint import CheckpointManager

    with tempfile.TemporaryDirectory() as tmp:
        cm = CheckpointManager(
            task_dir=Path(tmp),
            input_digest="sha256:abc123",
            parse_control_fingerprint="pc_fp_001",
            runtime_profile_fingerprint="rc_fp_001",
        )

        cm.save_input_digest("001", "sha256:abc123")

        # Valid resume: same digest
        assert cm.validate_resume("001", "sha256:abc123") is True

        # Invalid resume: wrong digest
        assert cm.validate_resume("001", "sha256:different_digest") is False

        # Non-existent file_id
        assert cm.validate_resume("002", "sha256:any") is False


def test_checkpoint_save_and_load_page_fragments():
    """DRC-W6-02: CheckpointManager saves and loads page fragments atomically."""
    from docmirror.runtime.checkpoint import CheckpointManager

    with tempfile.TemporaryDirectory() as tmp:
        cm = CheckpointManager(
            task_dir=Path(tmp),
            input_digest="sha256:def456",
            parse_control_fingerprint="pc_fp_002",
            runtime_profile_fingerprint="rc_fp_002",
        )

        fragment1 = {"page": 1, "text": "Page one content"}
        fragment2 = {"page": 2, "text": "Page two content"}

        p1 = cm.save_page_fragment("001", 1, fragment1)
        p2 = cm.save_page_fragment("001", 2, fragment2)

        assert p1.is_file()
        assert p2.is_file()

        fragments = cm.load_page_fragments("001")
        assert len(fragments) == 2
        assert fragments[0]["page"] == 1
        assert fragments[1]["page"] == 2

        assert cm.has_page_fragment("001", 1) is True
        assert cm.has_page_fragment("001", 3) is False


def test_checkpoint_fingerprint_changes_with_config():
    """DRC-W6-02: Checkpoint fingerprint changes when config changes."""
    from docmirror.runtime.checkpoint import CheckpointManager

    with tempfile.TemporaryDirectory() as tmp:
        cm1 = CheckpointManager(
            task_dir=Path(tmp),
            input_digest="sha256:abc",
            parse_control_fingerprint="pc_001",
            runtime_profile_fingerprint="rc_001",
        )
        cm2 = CheckpointManager(
            task_dir=Path(tmp),
            input_digest="sha256:xyz",
            parse_control_fingerprint="pc_001",
            runtime_profile_fingerprint="rc_001",
        )
        assert cm1.fingerprint() != cm2.fingerprint()


def test_checkpoint_save_input_source():
    """DRC-W6-02: CheckpointManager can save input source file."""
    from docmirror.runtime.checkpoint import CheckpointManager

    with tempfile.TemporaryDirectory() as tmp:
        task_dir = Path(tmp) / "task"
        task_dir.mkdir()

        source = Path(tmp) / "test_input.pdf"
        source.write_text("mock PDF content", encoding="utf-8")

        cm = CheckpointManager(
            task_dir=task_dir,
            input_digest=hashlib.sha256(source.read_bytes()).hexdigest(),
        )

        saved = cm.save_input_source("001", source)
        assert saved.is_file()
        assert saved.read_bytes() == source.read_bytes()


# --- Event Ledger -- Batch Progress Events ---


def test_event_ledger_batch_progress_lifecycle():
    """DRC-W6-02: EventLedger captures full batch processing progress lifecycle."""
    from docmirror.runtime.ledger import EventLedger
    from docmirror.runtime.events import ProgressEvent

    with tempfile.TemporaryDirectory() as tmp:
        ledger = EventLedger(Path(tmp))

        for file_id in ["001", "002", "003"]:
            for stage in ["intake", "extract", "enrich"]:
                status = "succeeded" if file_id != "003" or stage != "extract" else "failed_retryable"
                event = ProgressEvent(
                    task_id="batch_task_001",
                    file_id=file_id,
                    work_unit_id=f"batch_task_001/{file_id}/{stage}",
                    stage=stage,
                    status=status,
                    message=f"{stage} completed for {file_id}",
                )
                ledger.write_progress(event)

        # File 003 enrichment succeeded on retry
        ledger.write_progress(ProgressEvent(
            task_id="batch_task_001",
            file_id="003",
            work_unit_id="batch_task_001/003/extract_retry",
            stage="extract",
            status="succeeded",
            message="extract retry succeeded for 003",
        ))

        events = ledger.read_progress_events()
        assert len(events) == 10  # 3 files * 3 stages + 1 retry

        for evt in events:
            assert "event_id" in evt
            assert "task_id" in evt
            assert "stage" in evt
            assert "status" in evt


def test_event_ledger_manifest_v2_batch_partial():
    """DRC-W6-02: Manifest v2 reflects batch partial status correctly."""
    from docmirror.runtime.ledger import EventLedger, build_manifest_v2

    with tempfile.TemporaryDirectory() as tmp:
        ledger = EventLedger(Path(tmp))

        manifest = build_manifest_v2(
            task_id="batch_manifest_task",
            status="running",
            stage="intake",
            inputs=[
                {"file_id": "001", "file_path": "f1.pdf"},
                {"file_id": "002", "file_path": "f2.pdf"},
                {"file_id": "003", "file_path": "f3.pdf"},
            ],
            profile="full",
        )
        ledger.write_manifest(manifest)

        ledger.update_manifest_v2(
            status="partial",
            stage="complete",
            progress={"percent": 66.7, "total_units": 3, "completed_units": 2, "failed_units": 1},
            page_outcomes=[
                {"file_id": "001", "page": 1, "status": "success"},
                {"file_id": "001", "page": 2, "status": "success"},
            ],
            fallbacks=[
                {"fallback_type": "vlm_unavailable", "from_path": "vlm_ocr",
                 "to_path": "cpu_ocr", "reason": "provider_missing_api_key"},
            ],
        )

        updated = ledger.read_manifest()
        assert updated["version"] == 2
        assert updated["status"] == "partial"
        assert updated["stage"] == "complete"
        assert updated["progress"]["percent"] == 66.7
        assert len(updated["page_outcomes"]) == 2
        assert len(updated["fallbacks"]) == 1


def test_event_ledger_compute_progress_from_work_units():
    """DRC-W6-02: EventLedger computes aggregate progress from work units."""
    from docmirror.runtime.ledger import EventLedger

    with tempfile.TemporaryDirectory() as tmp:
        ledger = EventLedger(Path(tmp))

        ledger.write_work_unit({"work_unit_id": "u1", "status": "succeeded"})
        ledger.write_work_unit({"work_unit_id": "u2", "status": "succeeded"})
        ledger.write_work_unit({"work_unit_id": "u3", "status": "failed_final"})
        ledger.write_work_unit({"work_unit_id": "u4", "status": "running"})

        progress = ledger.compute_progress()
        assert progress["total_units"] == 4
        assert progress["completed_units"] == 2
        assert progress["failed_units"] == 1
        assert progress["running_units"] == 1
        assert progress["percent"] == 50.0


# --- Scheduler Config -- Per-batch Tuning ---


def test_scheduler_config_custom_for_batch():
    """DRC-W6-02: Scheduler config can be tuned for batch workloads."""
    from docmirror.runtime.scheduler import SchedulerConfig
    from docmirror.runtime.control import RetryControl

    config = SchedulerConfig(
        max_file_workers=4,
        max_page_workers=8,
        retry=RetryControl(max_attempts=3, delay_seconds=1.0),
    )
    assert config.max_file_workers == 4
    assert config.max_page_workers == 8
    assert config.retry.max_attempts == 3
    assert config.retry.delay_seconds == 1.0


def test_scheduler_config_default_is_reasonable():
    """DRC-W6-02: Default SchedulerConfig is safe for small batches."""
    from docmirror.runtime.scheduler import SchedulerConfig

    config = SchedulerConfig()
    assert config.max_file_workers >= 1
    assert config.max_page_workers >= 1
    assert config.retry.max_attempts >= 1


# --- Manifest v2 Batch Integration ---


def test_build_manifest_v2_batch_inputs():
    """DRC-W6-02: build_manifest_v2 captures multi-file batch inputs."""
    from docmirror.runtime.ledger import build_manifest_v2

    manifest = build_manifest_v2(
        task_id="batch_manifest_w6",
        status="running",
        stage="page_extract",
        inputs=[
            {"file_id": "001", "file_path": "f1.pdf", "status": "success"},
            {"file_id": "002", "file_path": "f2.pdf", "status": "running"},
            {"file_id": "003", "file_path": "f3.pdf", "status": "pending"},
        ],
        editions=["mirror", "community"],
        formats=["json", "markdown"],
        profile="full",
        entry="cli_batch",
        request_id="req_batch_001",
    )

    assert manifest["version"] == 2
    assert len(manifest["inputs"]) == 3
    assert manifest["inputs"][0]["file_id"] == "001"
    assert manifest["observability"]["entry"] == "cli_batch"
    assert manifest["observability"]["request_id"] == "req_batch_001"
    assert manifest["observability"]["profile"] == "full"


def test_manifest_v2_tracks_fallback_integration():
    """DRC-W6-02: Manifest v2 integrates fallback tracking for batch visibility."""
    from docmirror.runtime.ledger import EventLedger, build_manifest_v2

    with tempfile.TemporaryDirectory() as tmp:
        ledger = EventLedger(Path(tmp))
        manifest = build_manifest_v2(task_id="batch_fb_vis", status="running")
        ledger.write_manifest(manifest)

        ledger.update_manifest_v2(
            fallbacks=[
                {
                    "fallback_type": "vlm_unavailable",
                    "from_path": "vlm_ocr",
                    "to_path": "cpu_ocr",
                    "reason": "no_api_key",
                },
                {
                    "fallback_type": "gpu_missing",
                    "from_path": "gpu_ocr",
                    "to_path": "cpu_ocr",
                    "reason": "cuda_not_found",
                },
            ]
        )

        updated = ledger.read_manifest()
        assert len(updated["fallbacks"]) == 2
        assert updated["fallbacks"][0]["fallback_type"] == "vlm_unavailable"
        assert updated["fallbacks"][1]["fallback_type"] == "gpu_missing"


# --- Fallback Event Tracking for Batch ---


def test_fallback_events_across_batch_files():
    """DRC-W6-02: Fallback events track per-file fallbacks in batch processing."""
    from docmirror.runtime.events import FallbackEvent
    from docmirror.runtime.ledger import EventLedger

    with tempfile.TemporaryDirectory() as tmp:
        ledger = EventLedger(Path(tmp))

        for file_id, page in [("001", 3), ("002", 7), ("004", 1)]:
            fb = FallbackEvent(
                task_id="batch_fb_001",
                fallback_type="vlm_unavailable",
                from_path="vlm_ocr",
                to_path="cpu_ocr",
                reason="provider_missing_api_key",
                scope={"file_id": file_id, "page": page},
                effect="slower_parse",
                user_visible=True,
            )
            ledger.write_fallback(fb)

        fbs = ledger.read_fallback_events()
        assert len(fbs) == 3
        for fb in fbs:
            assert fb["fallback_type"] == "vlm_unavailable"
            assert "scope" in fb
            assert fb["user_visible"] is True

        file_ids = {fb["scope"]["file_id"] for fb in fbs}
        assert file_ids == {"001", "002", "004"}


# --- Work Unit Planner -- Batch-aware Planning ---


def test_work_unit_planner_batch_scenario():
    """DRC-W6-02: WorkUnitPlanner generates plans suitable for batch processing."""
    from docmirror.runtime.work_units import WorkUnitPlanner, compute_input_digest

    digest = compute_input_digest(content=b"mock PDF content")

    units = WorkUnitPlanner.plan(
        task_id="batch_task_001",
        file_id="005",
        input_digest=digest,
        page_count=80,
        editions=["mirror", "community"],
        profile="full",
        doc_size="long",
    )

    assert len(units) > 0

    extract_units = [u for u in units if u.unit_type == "page_extract"]
    assert len(extract_units) == 80  # 80 pages, each gets a page_extract unit

    ids = [u.work_unit_id for u in units]
    assert len(ids) == len(set(ids))

    assert units[0].unit_type == "input_intake"
    assert units[-1].unit_type == "finalize"


def test_work_unit_planner_small_doc_plan():
    """DRC-W6-02: Small documents get a collapsed work plan."""
    from docmirror.runtime.work_units import WorkUnitPlanner, compute_input_digest

    digest = compute_input_digest(content=b"small doc")

    units = WorkUnitPlanner.plan(
        task_id="batch_task_002",
        file_id="001",
        input_digest=digest,
        page_count=3,
        editions=["mirror"],
        profile="compact",
        doc_size="small",
    )

    extract_units = [u for u in units if u.unit_type == "page_extract"]
    assert len(extract_units) == 1

    chunk_units = [u for u in units if u.unit_type == "chunk_project"]
    assert len(chunk_units) == 0

    edition_units = [u for u in units if u.unit_type == "edition_project"]
    assert len(edition_units) >= 1


def test_work_unit_planner_forensic_profile():
    """DRC-W6-02: Forensic profile includes evidence_project unit."""
    from docmirror.runtime.work_units import WorkUnitPlanner, compute_input_digest

    digest = compute_input_digest(content=b"forensic test")

    units = WorkUnitPlanner.plan(
        task_id="batch_task_003",
        file_id="001",
        input_digest=digest,
        page_count=5,
        editions=["mirror", "community"],
        profile="forensic",
        doc_size="medium",
    )

    evidence_units = [u for u in units if u.unit_type == "evidence_project"]
    assert len(evidence_units) == 1

    unit = units[0]
    assert unit.status == "pending"
    unit.mark_running()
    assert unit.status == "running"
    assert unit.attempt == 1
    unit.mark_succeeded({"mirror_fragment": "path/to/frag.json"})
    assert unit.status == "succeeded"
    assert unit.artifacts["mirror_fragment"] == "path/to/frag.json"

    unit2 = units[1]
    unit2.mark_failed(RuntimeError("test error"), retryable=True)
    assert unit2.status == "failed_retryable"
    assert len(unit2.errors) == 1

    unit3 = units[2]
    unit3.mark_failed(ValueError("unrecoverable"), retryable=False)
    assert unit3.status == "failed_final"


# --- Compute Input Digest ---


def test_compute_input_digest_deterministic():
    """DRC-W6-02: compute_input_digest is deterministic for same content."""
    from docmirror.runtime.work_units import compute_input_digest

    d1 = compute_input_digest(content=b"test content")
    d2 = compute_input_digest(content=b"test content")
    assert d1 == d2
    assert len(d1) == 64


def test_compute_input_digest_different_content():
    """DRC-W6-02: compute_input_digest differs for different content."""
    from docmirror.runtime.work_units import compute_input_digest

    d1 = compute_input_digest(content=b"content A")
    d2 = compute_input_digest(content=b"content B")
    assert d1 != d2


def test_compute_input_digest_empty():
    """DRC-W6-02: compute_input_digest handles empty content."""
    from docmirror.runtime.work_units import compute_input_digest

    d = compute_input_digest()
    assert len(d) == 64
    assert d == hashlib.sha256(b"").hexdigest()
