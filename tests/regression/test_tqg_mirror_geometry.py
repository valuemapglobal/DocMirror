# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TQG mirror_geometry track regression."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.regression.conftest import _run_and_assert

pytestmark = [pytest.mark.tier_regression, pytest.mark.track_mirror_geometry]

try:
    from docmirror.eval.tqg.manifest import TQG_GATES_DIR, load_track_manifest

    REPO_ROOT = Path(__file__).resolve().parents[2]
    _MIRROR_GEOMETRY_CASES = load_track_manifest(
        TQG_GATES_DIR / "mirror_geometry.yaml",
        repo_root=REPO_ROOT,
    )
except Exception:
    _MIRROR_GEOMETRY_CASES = []


@pytest.mark.parametrize("case", _MIRROR_GEOMETRY_CASES, ids=lambda c: c.id)
def test_tqg_mirror_geometry_case(case, tqg_report_dir):
    _run_and_assert(case, tqg_report_dir)
