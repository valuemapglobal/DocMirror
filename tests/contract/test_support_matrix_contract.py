# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from tools.validate_support_matrix import validate_support_matrix


def test_support_matrix_matches_fcr():
    assert validate_support_matrix() == []
