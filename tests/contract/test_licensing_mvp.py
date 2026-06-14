# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""MVP licensing contract regression (doc 13 §5)."""

from __future__ import annotations

import re

from docmirror.plugins.licensing.entitlements import demo_features


def test_demo_features_match_premium_pattern_or_literals():
    features = demo_features()
    premium_re = re.compile(r"^[a-z0-9_]+_premium$")
    literals = {"batch_processing", "priority_support"}
    for feat in features:
        assert premium_re.match(feat) or feat in literals
