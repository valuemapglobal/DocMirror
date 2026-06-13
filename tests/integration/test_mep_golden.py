# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Legacy dual-run shim — MEP golden profiles delegate to TQG mirror track."""

from __future__ import annotations

import pytest

from tests.regression.conftest import _MIRROR_CASES, _run_and_assert

pytestmark = [
    pytest.mark.tier_regression,
    pytest.mark.track_mirror,
    pytest.mark.track_classify,
    pytest.mark.integration,
]


@pytest.mark.parametrize("case", _MIRROR_CASES, ids=lambda c: c.id)
def test_mep_golden_tqg(case, tqg_report_dir):
    """Thin wrapper over configs/yaml/test/gates/mirror.yaml (replaces mep_profiles.yaml loops)."""
    _run_and_assert(case, tqg_report_dir)
