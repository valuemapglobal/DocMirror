# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for layout profile institution variants."""

from docmirror.core.layout.profile_registry import (
    get_profile,
    load_profiles,
    match_institution_variant,
    resolve_header_aliases,
)


def test_bank_profile_institution_variants():
    load_profiles.cache_clear()
    profile = get_profile("borderless_ledger_bank")
    assert profile.institution_variants
    variant = match_institution_variant(profile, "中国建设银行账户明细信息")
    assert variant is not None
    assert variant.id == "ccb"
    assert variant.column_map.get("交易日期") == "交易时间"


def test_header_aliases_resolve():
    load_profiles.cache_clear()
    profile = get_profile("borderless_ledger_bank")
    assert resolve_header_aliases(profile, "交易日期") == "交易时间"
    assert resolve_header_aliases(profile, "交易日") == "交易时间"
