# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Legacy dual-run shim — edition track delegates to TQG edition.yaml."""

from __future__ import annotations

import pytest

from tests.regression.conftest import _EDITION_CASES, _run_and_assert

pytestmark = [
    pytest.mark.tier_regression,
    pytest.mark.track_edition,
    pytest.mark.integration,
]


@pytest.mark.parametrize("case", _EDITION_CASES, ids=lambda c: c.id)
def test_edition_golden_tqg(case, tqg_report_dir):
    """Thin wrapper over configs/yaml/test/gates/edition.yaml."""
    _run_and_assert(case, tqg_report_dir)
