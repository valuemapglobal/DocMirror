# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest

from docmirror.eval.tqg.manifest import TQG_GATES_DIR, load_track_manifest
from tests.regression.conftest import _run_and_assert

_CASES = load_track_manifest(TQG_GATES_DIR / "scanned_micro_grid.yaml")


@pytest.mark.parametrize("case", _CASES, ids=lambda c: c.id)
def test_tqg_scanned_micro_grid_case(case, tqg_report_dir):
    _run_and_assert(case, tqg_report_dir)
