# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Strategy registry thin wrappers (Phase 4)."""

from __future__ import annotations

from docmirror.core.extraction.strategies.strategy_registry import get_strategy


def test_table_dominant_registered():
    import docmirror.core.extraction.strategies.table_led  # noqa: F401

    strategy = get_strategy("table_dominant")
    assert strategy is not None
    assert strategy.__class__.__name__ == "TableLedStrategy"


def test_scanned_registered():
    import docmirror.core.extraction.strategies.scanned  # noqa: F401

    strategy = get_strategy("scanned")
    assert strategy is not None
    assert strategy.__class__.__name__ == "ScannedStrategy"


def test_mixed_registered():
    import docmirror.core.extraction.strategies.mixed  # noqa: F401

    strategy = get_strategy("mixed")
    assert strategy is not None
    assert strategy.__class__.__name__ == "MixedStrategy"


def test_text_dominant_registered():
    import docmirror.core.extraction.strategies.text_dominant  # noqa: F401

    strategy = get_strategy("text_dominant")
    assert strategy is not None
    assert strategy.__class__.__name__ == "TextDominantStrategy"
