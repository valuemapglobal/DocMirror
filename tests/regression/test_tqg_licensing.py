# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TQG licensing track regression — parametrized from licensing.yaml."""

from __future__ import annotations

import pytest

from tests.regression.conftest import _LICENSING_CASES, _run_and_assert


@pytest.mark.parametrize("case", _LICENSING_CASES, ids=lambda c: c.id)
def test_tqg_licensing_case(case, tqg_report_dir):
    _run_and_assert(case, tqg_report_dir)
