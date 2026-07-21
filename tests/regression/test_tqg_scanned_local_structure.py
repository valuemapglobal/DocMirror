# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest

from docmirror.eval.tqg.manifest import TQG_GATES_DIR, load_track_manifest
from tests.regression.conftest import _run_and_assert

_CASES = load_track_manifest(TQG_GATES_DIR / "scanned_local_structure.yaml")


@pytest.mark.track_scanned_local_structure
@pytest.mark.parametrize("case", _CASES, ids=lambda c: c.id)
def test_tqg_scanned_local_structure_case(case, tqg_report_dir):
    _run_and_assert(case, tqg_report_dir)
