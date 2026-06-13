# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TQG e2e track — four-file output and CLI contract gates from e2e.yaml."""

from __future__ import annotations

import pytest

from tests.regression.conftest import _E2E_CASES, _run_and_assert


def _e2e_params():
    params = []
    for case in _E2E_CASES:
        marks = [pytest.mark.track_e2e]
        if case.tier == "contract":
            marks.append(pytest.mark.tier_contract)
        else:
            marks.append(pytest.mark.tier_regression)
        params.append(pytest.param(case, id=case.id, marks=marks))
    return params


@pytest.mark.parametrize("case", _e2e_params())
def test_tqg_e2e_case(case, tqg_report_dir):
    _run_and_assert(case, tqg_report_dir)
