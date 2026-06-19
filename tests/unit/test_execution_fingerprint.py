# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for execution fingerprint cache keys."""

from __future__ import annotations

from docmirror.core.entry.options import ParseControl
from docmirror.framework.execution_fingerprint import (
    build_execution_fingerprint,
    invalidate_pipeline_fingerprint_cache,
    pipeline_version_fingerprint,
)


def test_pipeline_version_fingerprint_stable():
    invalidate_pipeline_fingerprint_cache()
    a = pipeline_version_fingerprint()
    b = pipeline_version_fingerprint()
    assert a == b
    assert len(a) == 16


def test_execution_fingerprint_includes_control_and_pipeline():
    invalidate_pipeline_fingerprint_cache()
    control = ParseControl()
    fp1 = build_execution_fingerprint(control)
    fp2 = build_execution_fingerprint(control)
    assert fp1 == fp2
    assert len(fp1) == 24
    assert fp1 != control.fingerprint()


def test_execution_fingerprint_changes_with_control():
    invalidate_pipeline_fingerprint_cache()
    fp_a = build_execution_fingerprint(ParseControl(mode="fast"))
    fp_b = build_execution_fingerprint(ParseControl(mode="forensic"))
    assert fp_a != fp_b
