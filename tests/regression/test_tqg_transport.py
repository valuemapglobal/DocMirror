# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TQG transport track — parametrized from transport.yaml (FCR smoke gates)."""

from __future__ import annotations

import pytest

from tests.regression.conftest import _TRANSPORT_CASES, _run_and_assert

pytestmark = [pytest.mark.tier_smoke, pytest.mark.track_transport]


@pytest.mark.parametrize("case", _TRANSPORT_CASES, ids=lambda c: c.id)
def test_tqg_transport_case(case, tqg_report_dir):
    _run_and_assert(case, tqg_report_dir)
