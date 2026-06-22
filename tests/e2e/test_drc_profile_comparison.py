# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""DRC Wave 4: Cost Profile Comparison e2e tests.

GA 1.0 DRC-W4-05: Proves that compact/full/forensic profiles produce
measurably different outputs that match the profile contract.
"""

from __future__ import annotations

import json

import pytest


def test_three_profiles_resolve():
    """DRC-W4-01: Three profiles resolve to distinct ProfileResolution."""
    from docmirror.runtime.profiles import (
        COMPACT_PROFILE,
        FULL_PROFILE,
        FORENSIC_PROFILE,
        resolve_profile,
    )

    c = resolve_profile("compact")
    f = resolve_profile("full")
    fr = resolve_profile("forensic")

    # Profiles differ
    assert c.mirror_level != fr.mirror_level        # standard vs forensic
    assert c.geometry != fr.geometry                # block vs full
    assert fr.evidence_depth != c.evidence_depth     # always equal, but check profile_name
    assert c.profile_name == "compact"
    assert fr.profile_name == "forensic"

    # Token budget differs
    assert c.token_budget_hard_limit < f.token_budget_hard_limit
    assert f.token_budget_hard_limit < fr.token_budget_hard_limit

    # Chunk strategy differs
    assert c.chunk_strategy == "large"
    assert f.chunk_strategy == "normal"
    assert fr.chunk_strategy == "small"


def test_profile_diff_shows_differences():
    """DRC-W4-01: profile_diff reports differences between profiles."""
    from docmirror.runtime.profiles import (
        COMPACT_PROFILE,
        FORENSIC_PROFILE,
        profile_diff,
    )

    diff = profile_diff(COMPACT_PROFILE, FORENSIC_PROFILE)
    assert len(diff) > 0  # There should be differences
    # Check specific known differences
    assert "mirror_level" in diff
    assert diff["mirror_level"]["from"] == "standard"
    assert diff["mirror_level"]["to"] == "forensic"


def test_profile_from_cli_default():
    """DRC-W4-01: profile_from_cli defaults to full."""
    from docmirror.runtime.profiles import profile_from_cli

    p = profile_from_cli(None)
    assert p.profile_name == "full"

    p = profile_from_cli("compact")
    assert p.profile_name == "compact"


def test_unknown_profile_falls_back():
    """DRC-W4-01: Unknown profile falls back to full."""
    from docmirror.runtime.profiles import resolve_profile

    p = resolve_profile("nonexistent_v999")
    assert p.profile_name == "full"  # fallback


def test_runtime_control_factory_methods():
    """DRC-W4-01: RuntimeControl factory methods produce correct profiles."""
    from docmirror.runtime.control import RuntimeControl

    compact = RuntimeControl.compact()
    assert compact.cost_profile == "compact"
    assert compact.streaming.chunk_artifacts is False
    assert compact.token_budget.hard_limit == 100_000

    full = RuntimeControl.full()
    assert full.cost_profile == "full"
    assert full.streaming.page_artifacts is True
    assert full.token_budget.hard_limit == 200_000

    forensic = RuntimeControl.forensic()
    assert forensic.cost_profile == "forensic"
    assert forensic.streaming.chunk_artifacts is True
    assert forensic.token_budget.hard_limit == 500_000


def test_runtime_control_fingerprint_stable():
    """DRC-W4-01: Fingerprint is stable for same config."""
    from docmirror.runtime.control import RuntimeControl

    a = RuntimeControl.full()
    b = RuntimeControl.full()
    assert a.fingerprint() == b.fingerprint()

    # Different config gives different fingerprint
    c = RuntimeControl.compact()
    assert a.fingerprint() != c.fingerprint()


# ── Artifact size guards ────────────────────────────────────────────────


def test_intermediate_artifact_size_guards():
    """DRC-W4-03: IntermediateArtifactWriter has size guards per profile."""
    from docmirror.runtime.artifacts import (
        IntermediateArtifactWriter,
        PROFILE_SIZE_GUARDS,
    )

    assert "compact" in PROFILE_SIZE_GUARDS
    assert "full" in PROFILE_SIZE_GUARDS
    assert "forensic" in PROFILE_SIZE_GUARDS

    # compact guard is smaller
    assert PROFILE_SIZE_GUARDS["compact"] < PROFILE_SIZE_GUARDS["full"]

    # forensic guard is largest
    assert PROFILE_SIZE_GUARDS["forensic"] > PROFILE_SIZE_GUARDS["full"]


def test_artifact_writer_size_tracking():
    """DRC-W4-03: Writer tracks total bytes and warns over budget."""
    import tempfile
    from pathlib import Path
    from docmirror.runtime.artifacts import IntermediateArtifactWriter

    with tempfile.TemporaryDirectory() as tmp:
        writer = IntermediateArtifactWriter(Path(tmp), profile="compact")

        # Write a small fragment
        data = {"key": "value" * 1000}
        writer.write_page_mirror_fragment("001", 1, data)

        status = writer.check_size_guard()
        assert status["profile"] == "compact"
        assert status["total_bytes_written"] > 0
        # Should not be over budget for a small fragment
        assert status["over_budget"] is False


# ── Token estimation ────────────────────────────────────────────────────


def test_estimate_tokens():
    """DRC-W4-02: Token estimation produces reasonable counts."""
    from docmirror.runtime.metrics import estimate_tokens

    # Empty
    assert estimate_tokens("") == 0

    # Short text
    assert estimate_tokens("Hello") >= 1

    # Longer text — roughly 1 token per 3-4 chars
    text = "The quick brown fox " * 50
    estimated = estimate_tokens(text)
    assert estimated > 0


# ── Manifest v2 profile propagation ─────────────────────────────────────


def test_manifest_v2_includes_profile():
    """DRC-W4-05: Manifest v2 includes runtime profile."""
    from docmirror.runtime.ledger import build_manifest_v2

    runtime_dict = {"cost_profile": "forensic", "task_mode": "async"}
    manifest = build_manifest_v2(
        task_id="test_profile_001",
        status="running",
        stage="page_extract",
        runtime_control=runtime_dict,
    )
    assert manifest["version"] == 2
    assert manifest["runtime"]["cost_profile"] == "forensic"
    assert manifest["stage"] == "page_extract"


# ── TaskResult v2 compatibility ─────────────────────────────────────────


def test_task_result_v2_from_manifest():
    """DRC-W4-05: TaskResult can read v2 manifests."""
    import tempfile
    from pathlib import Path
    from docmirror.server.task_result import task_result_from_manifest

    with tempfile.TemporaryDirectory() as tmp:
        manifest_path = Path(tmp) / "manifest.json"
        manifest_data = {
            "version": 2,
            "task_id": "test_tr_001",
            "status": "partial",
            "stage": "complete",
            "runtime": {"cost_profile": "full"},
            "progress": {"percent": 75.0},
            "inputs": [{"file_id": "001", "file_path": "doc.pdf", "status": "success"}],
            "artifacts": {"mirror": "001_mirror.json"},
            "errors": [],
        }
        manifest_path.write_text(json.dumps(manifest_data))

        tr = task_result_from_manifest(manifest_path)
        assert tr.version == 2
        assert tr.status == "partial"
        assert tr.stage == "complete"
        assert tr.runtime["cost_profile"] == "full"
        assert tr.progress["percent"] == 75.0


# ── Batch job ledger ────────────────────────────────────────────────────


def test_batch_job_ledger_lifecycle():
    """DRC-W2-01: BatchJobLedger tracks files through lifecycle."""
    from docmirror.runtime.work_units import BatchJobLedger, BatchJobEntry

    ledger = BatchJobLedger(batch_id="batch_001", task_id="batch_001_task")
    entry = BatchJobEntry(
        file_id="001",
        file_path="doc1.pdf",
        status="pending",
    )
    ledger.add_entry(entry)
    ledger.mark_running("001")
    assert ledger.get_entry("001").status == "running"

    ledger.mark_succeeded("001", {"mirror": "001_mirror.json"})
    assert ledger.get_entry("001").status == "succeeded"
    assert ledger.get_entry("001").artifacts["mirror"] == "001_mirror.json"

    progress = ledger.compute_progress()
    assert progress["total"] == 1
    assert progress["succeeded"] == 1


# ── Scheduler config ────────────────────────────────────────────────────


def test_scheduler_config_defaults():
    """DRC-W2-02: SchedulerConfig has reasonable defaults."""
    from docmirror.runtime.scheduler import SchedulerConfig

    config = SchedulerConfig()
    assert config.max_file_workers == 2
    assert config.max_page_workers == 4
    assert config.retry.max_attempts == 2



# ============================================================================
# DRC-W6-04: Profile Comparison Demo — side-by-side output differences
# ============================================================================


def test_w6_profile_comparison_matrix():
    """DRC-W6-04: Full comparison matrix compact vs full vs forensic."""
    from docmirror.runtime.profiles import (
        COMPACT_PROFILE, FULL_PROFILE, FORENSIC_PROFILE,
        resolve_profile, profile_diff,
    )

    # Resolve all three
    compact = resolve_profile("compact")
    full = resolve_profile("full")
    forensic = resolve_profile("forensic")

    # --- compact vs full ---
    c_f_diff = profile_diff(compact, full)
    assert len(c_f_diff) >= 3  # At least geometry, evidence_depth, visual_debug differ
    # mirror_level is the same for compact and full, so not in diff
    assert c_f_diff["geometry"]["from"] == "block"
    assert c_f_diff["geometry"]["to"] == "token"
    assert c_f_diff["evidence_depth"]["from"] == "basic"
    assert c_f_diff["evidence_depth"]["to"] == "full"

    # --- full vs forensic ---
    f_fr_diff = profile_diff(full, forensic)
    assert len(f_fr_diff) >= 3
    assert f_fr_diff["mirror_level"]["from"] == "standard"
    assert f_fr_diff["mirror_level"]["to"] == "forensic"
    assert f_fr_diff["geometry"]["from"] == "token"
    assert f_fr_diff["geometry"]["to"] == "full"

    # --- compact vs forensic (maximum distance) ---
    c_fr_diff = profile_diff(compact, forensic)
    # This should have the most differences
    assert len(c_fr_diff) >= len(c_f_diff)
    assert len(c_fr_diff) >= len(f_fr_diff)


def test_w6_profile_comparison_token_budget_ordering():
    """DRC-W6-04: Token budgets are strictly ordered: compact < full < forensic."""
    from docmirror.runtime.profiles import COMPACT_PROFILE, FULL_PROFILE, FORENSIC_PROFILE

    assert COMPACT_PROFILE.token_budget_hard_limit < FULL_PROFILE.token_budget_hard_limit
    assert FULL_PROFILE.token_budget_hard_limit < FORENSIC_PROFILE.token_budget_hard_limit

    # Verify exact values
    assert COMPACT_PROFILE.token_budget_hard_limit == 100_000
    assert FULL_PROFILE.token_budget_hard_limit == 200_000
    assert FORENSIC_PROFILE.token_budget_hard_limit == 500_000


def test_w6_profile_comparison_chunk_strategy():
    """DRC-W6-04: Chunk strategies differ: large > normal > small."""
    from docmirror.runtime.profiles import COMPACT_PROFILE, FULL_PROFILE, FORENSIC_PROFILE

    # compact: large chunks (fewer, bigger)
    assert COMPACT_PROFILE.chunk_strategy == "large"
    assert COMPACT_PROFILE.max_chunk_chars == 3000
    assert COMPACT_PROFILE.chunk_overlap == 100

    # full: normal chunks
    assert FULL_PROFILE.chunk_strategy == "normal"
    assert FULL_PROFILE.max_chunk_chars == 2000
    assert FULL_PROFILE.chunk_overlap == 200

    # forensic: small chunks (more, smaller, more overlap)
    assert FORENSIC_PROFILE.chunk_strategy == "small"
    assert FORENSIC_PROFILE.max_chunk_chars == 1000
    assert FORENSIC_PROFILE.chunk_overlap == 400


def test_w6_profile_comparison_size_guards():
    """DRC-W6-04: Output size guards are strictly ordered."""
    from docmirror.runtime.profiles import COMPACT_PROFILE, FULL_PROFILE, FORENSIC_PROFILE

    compact_guard = COMPACT_PROFILE.output_size_guard_bytes
    full_guard = FULL_PROFILE.output_size_guard_bytes
    forensic_guard = FORENSIC_PROFILE.output_size_guard_bytes

    assert compact_guard < full_guard
    assert full_guard < forensic_guard

    # Verify magnitudes
    assert compact_guard == 20 * 1024 * 1024   # 20 MB
    assert full_guard == 100 * 1024 * 1024      # 100 MB
    assert forensic_guard == 500 * 1024 * 1024   # 500 MB


def test_w6_profile_comparison_visual_debug():
    """DRC-W6-04: Visual debug policy escalates with profile."""
    from docmirror.runtime.profiles import COMPACT_PROFILE, FULL_PROFILE, FORENSIC_PROFILE

    # compact: only on failure
    assert COMPACT_PROFILE.visual_debug == "failure_only"

    # full: sample failures
    assert FULL_PROFILE.visual_debug == "failure_sample"

    # forensic: all pages
    assert FORENSIC_PROFILE.visual_debug == "all"


def test_w6_profile_comparison_vlm_policy():
    """DRC-W6-04: VLM policy is off/optional/optional_strict."""
    from docmirror.runtime.profiles import COMPACT_PROFILE, FULL_PROFILE, FORENSIC_PROFILE

    # compact: VLM off to save cost
    assert COMPACT_PROFILE.vlm_policy == "off"

    # full: VLM optional (use if available)
    assert FULL_PROFILE.vlm_policy == "optional"

    # forensic: VLM optional but with strict provenance
    assert FORENSIC_PROFILE.vlm_policy == "optional_strict"


def test_w6_profile_comparison_runtime_control_factories():
    """DRC-W6-04: RuntimeControl factory methods map to correct profiles."""
    from docmirror.runtime.control import RuntimeControl

    compact = RuntimeControl.compact()
    full = RuntimeControl.full()
    forensic = RuntimeControl.forensic()

    # compact
    assert compact.cost_profile == "compact"
    assert compact.streaming.chunk_artifacts is False
    assert compact.streaming.page_artifacts is False
    assert compact.token_budget.hard_limit == 100_000

    # full
    assert full.cost_profile == "full"
    assert full.streaming.page_artifacts is True
    assert full.token_budget.hard_limit == 200_000

    # forensic
    assert forensic.cost_profile == "forensic"
    assert forensic.streaming.chunk_artifacts is True
    assert forensic.streaming.page_artifacts is True
    assert forensic.token_budget.hard_limit == 500_000


def test_w6_profile_comparison_unknown_profile_fallback():
    """DRC-W6-04: Unknown profile names gracefully fall back to 'full'."""
    from docmirror.runtime.profiles import resolve_profile, FULL_PROFILE

    # Various unknown names
    for bad_name in ["", "nonexistent", "BANANA", "MISSING", "something_else"]:
        resolved = resolve_profile(bad_name)
        # Should fall back to full
        assert resolved.profile_name == "full"


def test_w6_profile_comparison_to_dict_consistency():
    """DRC-W6-04: to_dict() roundtrip is consistent with original values."""
    import json
    from docmirror.runtime.profiles import COMPACT_PROFILE, FULL_PROFILE, FORENSIC_PROFILE

    for profile in [COMPACT_PROFILE, FULL_PROFILE, FORENSIC_PROFILE]:
        d = profile.to_dict()
        assert d["profile_name"] == profile.profile_name
        assert d["token_budget_hard_limit"] == profile.token_budget_hard_limit
        assert d["chunk_strategy"] == profile.chunk_strategy
        assert d["vlm_policy"] == profile.vlm_policy

        # Should be JSON serializable
        json_str = json.dumps(d, ensure_ascii=False)
        restored = json.loads(json_str)
        assert restored["profile_name"] == profile.profile_name


def test_w6_profile_comparison_estimate_tokens_per_profile():
    """DRC-W6-04: Token estimation interacts correctly with profile budgets."""
    from docmirror.runtime.profiles import COMPACT_PROFILE, FULL_PROFILE, FORENSIC_PROFILE
    from docmirror.runtime.metrics import estimate_tokens

    # Simulate document text of varying sizes
    small_text = "Hello world. " * 50    # ~150 tokens
    medium_text = "The quick brown fox jumps over the lazy dog. " * 100  # ~1000 tokens
    large_text = "DocMirror GA 1.0 is a universal document parser. " * 500  # ~4000 tokens

    profiles = {
        "compact": (COMPACT_PROFILE, small_text),
        "full": (FULL_PROFILE, medium_text),
        "forensic": (FORENSIC_PROFILE, large_text),
    }

    for name, (profile, text) in profiles.items():
        estimated = estimate_tokens(text)
        assert estimated > 0
        # Each profile should accommodate its expected text size
        assert estimated < profile.token_budget_hard_limit, (
            f"{name}: estimated {estimated} >= limit {profile.token_budget_hard_limit}"
        )


def test_w6_profile_comparison_evidence_depth_diff():
    """DRC-W6-04: Evidence depth is basic for compact, full otherwise."""
    from docmirror.runtime.profiles import COMPACT_PROFILE, FULL_PROFILE, FORENSIC_PROFILE

    assert COMPACT_PROFILE.evidence_depth == "basic"
    assert FULL_PROFILE.evidence_depth == "full"
    assert FORENSIC_PROFILE.evidence_depth == "full"


def test_w6_profile_comparison_geometry_diff():
    """DRC-W6-04: Geometry granularity: block < token < full."""
    from docmirror.runtime.profiles import COMPACT_PROFILE, FULL_PROFILE, FORENSIC_PROFILE

    assert COMPACT_PROFILE.geometry == "block"
    assert FULL_PROFILE.geometry == "token"
    assert FORENSIC_PROFILE.geometry == "full"


def test_w6_profile_comparison_mirror_level_diff():
    """DRC-W6-04: Mirror level: standard for compact/full, forensic for forensic."""
    from docmirror.runtime.profiles import COMPACT_PROFILE, FULL_PROFILE, FORENSIC_PROFILE

    assert COMPACT_PROFILE.mirror_level == "standard"
    assert FULL_PROFILE.mirror_level == "standard"
    assert FORENSIC_PROFILE.mirror_level == "forensic"


def test_w6_profile_comparison_output_controls_by_profile():
    """DRC-W6-04: Profile resolution produces distinct output controls."""
    from docmirror.runtime.profiles import resolve_profile
    from docmirror.runtime.control import RuntimeControl

    # compact: minimal output
    compact_rc = RuntimeControl.compact()
    assert compact_rc.cost_profile == "compact"
    assert compact_rc.checkpoint.enabled is True
    assert compact_rc.streaming.page_artifacts is False

    # full: standard output
    full_rc = RuntimeControl.full()
    assert full_rc.cost_profile == "full"
    assert full_rc.streaming.page_artifacts is True

    # forensic: everything
    forensic_rc = RuntimeControl.forensic()
    assert forensic_rc.cost_profile == "forensic"
    assert forensic_rc.checkpoint.enabled is True
    assert forensic_rc.streaming.page_artifacts is True
    assert forensic_rc.streaming.chunk_artifacts is True
