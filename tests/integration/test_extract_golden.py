# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Extract profile smoke tests not covered by the TQG manifest runner."""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.tier_regression,
    pytest.mark.track_extract,
    pytest.mark.integration,
]

def test_wechat_profile_grid_template_enabled():
    """P4-1: grid template enabled after BCS + row filtering fixes."""
    from docmirror.layout.profile.registry import get_profile

    profile = get_profile("borderless_ledger_wechat")
    assert profile.enable_grid_template is True
    assert profile.use_tnp_staged is True
    alipay = get_profile("borderless_ledger_alipay")
    assert alipay.enable_grid_template is True
    assert alipay.use_tnp_staged is True
