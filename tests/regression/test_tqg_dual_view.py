# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TQG dual_view track regression."""

from __future__ import annotations

import pytest

from tests.regression.conftest import _run_and_assert

pytestmark = [pytest.mark.tier_regression, pytest.mark.track_dual_view]

try:
    from pathlib import Path

    from docmirror.eval.tqg.manifest import TQG_GATES_DIR, load_track_manifest

    REPO_ROOT = Path(__file__).resolve().parents[2]
    _DUAL_VIEW_CASES = load_track_manifest(
        TQG_GATES_DIR / "dual_view.yaml",
        repo_root=REPO_ROOT,
    )
except Exception:
    _DUAL_VIEW_CASES = []


@pytest.mark.parametrize("case", _DUAL_VIEW_CASES, ids=lambda c: c.id)
def test_tqg_dual_view_case(case, tqg_report_dir):
    _run_and_assert(case, tqg_report_dir)
