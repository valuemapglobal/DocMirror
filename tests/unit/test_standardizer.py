# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for docmirror.plugins._base.standardizer."""

from __future__ import annotations

import pytest

from docmirror.plugins._base.standardizer import normalize_amount, normalize_timestamp

pytestmark = pytest.mark.unit


class TestNormalizeTimestamp:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2022-09-2810:30:39", "2022-09-28T10:30:39"),
            ("2022-09-2807:20:43", "2022-09-28T07:20:43"),
            ("2022-09-28 10:30:39", "2022-09-28T10:30:39"),
            ("2022-09-28 10:30", "2022-09-28T10:30:00"),
            ("2022-09-28", "2022-09-28T00:00:00"),
            ("2022/09/28 10:30:39", "2022-09-28T10:30:39"),
            ("20220928 103039", "2022-09-28T10:30:39"),
            ("2022-09-28T10:30:39", "2022-09-28T10:30:39"),
            ("", ""),
        ],
    )
    def test_normalize_timestamp_formats(self, raw: str, expected: str):
        assert normalize_timestamp(raw) == expected

    def test_unparseable_passthrough(self):
        assert normalize_timestamp("not-a-date") == "not-a-date"


class TestNormalizeAmount:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("¥1,234.56", 1234.56),
            ("+100.00", 100.0),
            ("", None),
        ],
    )
    def test_normalize_amount(self, raw: str, expected: float | None):
        assert normalize_amount(raw) == expected
