# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TQG bank_statement track regression."""

from __future__ import annotations

import pytest

from tests.regression.conftest import _run_and_assert

pytestmark = [pytest.mark.tier_regression, pytest.mark.track_bank_statement]

try:
    from docmirror.eval.tqg.manifest import TQG_GATES_DIR, load_track_manifest
    from pathlib import Path

    REPO_ROOT = Path(__file__).resolve().parents[2]
    _BANK_STATEMENT_CASES = load_track_manifest(
        TQG_GATES_DIR / "bank_statement.yaml",
        repo_root=REPO_ROOT,
    )
except Exception:
    _BANK_STATEMENT_CASES = []


@pytest.mark.parametrize("case", _BANK_STATEMENT_CASES, ids=lambda c: c.id)
def test_tqg_bank_statement_case(case, tqg_report_dir):
    _run_and_assert(case, tqg_report_dir)
