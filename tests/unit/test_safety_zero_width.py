# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for ZeroWidthDetector (GA1.0-ODL-04)."""

from __future__ import annotations

import pytest

from docmirror.security.safety.zero_width import (
    ZERO_WIDTH_CHARS,
    ZeroWidthDetector,
    ZeroWidthFlag,
)

pytestmark = [pytest.mark.tier_unit]


class TestZeroWidthDetector:
    """Suite of tests for zero-width character detection."""

    def test_detect_clean_text_returns_empty(self):
        detector = ZeroWidthDetector()
        flags = detector.detect("Hello, world!")
        assert flags == []

    def test_detect_empty_string(self):
        detector = ZeroWidthDetector()
        assert detector.detect("") == []
        assert detector.detect("   ") == []

    def test_detect_zero_width_space(self):
        detector = ZeroWidthDetector()
        text = "Hello\u200BWorld"
        flags = detector.detect(text)
        assert len(flags) == 1
        assert flags[0].char == "\u200B"
        assert flags[0].char_name == "ZERO_WIDTH_SPACE"
        assert flags[0].position == 5

    def test_detect_multiple_zero_width_chars(self):
        detector = ZeroWidthDetector()
        text = "A\u200BB\u200CC\uFEFF"
        flags = detector.detect(text)
        assert len(flags) == 3
        names = {f.char_name for f in flags}
        assert "ZERO_WIDTH_SPACE" in names
        assert "ZERO_WIDTH_NON_JOINER" in names
        assert "BOM_ZERO_WIDTH_NO_BREAK_SPACE" in names

    def test_detect_all_catalogued_chars(self):
        detector = ZeroWidthDetector()
        # Concatenate every zero-width char
        text = "".join(ZERO_WIDTH_CHARS.keys())
        flags = detector.detect(text)
        assert len(flags) == len(ZERO_WIDTH_CHARS)

    def test_detect_provides_context(self):
        detector = ZeroWidthDetector()
        text = "before\u200Bafter"
        flags = detector.detect(text)
        assert len(flags) == 1
        assert "before" in flags[0].context
        assert "after" in flags[0].context

    # ── sanitize() ─────────────────────────────────────────────────────

    def test_sanitize_remove_mode(self):
        detector = ZeroWidthDetector()
        text = "Hello\u200BWorld\uFEFF!"
        clean = detector.sanitize(text, mode="remove")
        assert clean == "HelloWorld!"

    def test_sanitize_clean_text_unchanged(self):
        detector = ZeroWidthDetector()
        clean = detector.sanitize("Hello, world!", mode="remove")
        assert clean == "Hello, world!"

    def test_sanitize_remove_multiple(self):
        detector = ZeroWidthDetector()
        text = "\u200B\u200C\u200D"  # all zero-width
        clean = detector.sanitize(text, mode="remove")
        assert clean == ""

    def test_sanitize_replace_mode(self):
        detector = ZeroWidthDetector()
        text = "A\u200BB"
        # Replace mode maps zero-width to ""
        clean = detector.sanitize(text, mode="replace")
        assert clean == "AB"

    def test_sanitize_invalid_mode_raises(self):
        detector = ZeroWidthDetector()
        with pytest.raises(ValueError, match="Unknown sanitize mode"):
            detector.sanitize("test", mode="nonexistent")

    def test_sanitize_default_mode_is_remove(self):
        detector = ZeroWidthDetector()
        clean = detector.sanitize("\u200Bhello\u200B")
        assert clean == "hello"

    # ── count() ────────────────────────────────────────────────────────

    def test_count_zero(self):
        detector = ZeroWidthDetector()
        assert detector.count("Hello, world!") == 0

    def test_count_multiple(self):
        detector = ZeroWidthDetector()
        text = "\u200B\u200B\u200B"
        assert detector.count(text) == 3

    def test_count_mixed(self):
        detector = ZeroWidthDetector()
        text = "ab\u200Bc\u200Cd"
        assert detector.count(text) == 2


class TestZeroWidthFlag:
    """ZeroWidthFlag data-class behaviour."""

    def test_default_values(self):
        flag = ZeroWidthFlag()
        assert flag.char == ""
        assert flag.char_name == ""
        assert flag.position == 0
        assert flag.context == ""

    def test_construction(self):
        flag = ZeroWidthFlag(
            char="\u200B",
            char_name="ZERO_WIDTH_SPACE",
            position=5,
            context="context snippet",
        )
        assert flag.char == "\u200B"
        assert flag.char_name == "ZERO_WIDTH_SPACE"
        assert flag.position == 5
        assert flag.context == "context snippet"


class TestZeroWidthCharsConstant:
    """ZERO_WIDTH_CHARS catalog completeness."""

    def test_non_empty(self):
        assert len(ZERO_WIDTH_CHARS) > 10

    def test_all_keys_are_single_chars(self):
        for c in ZERO_WIDTH_CHARS:
            assert len(c) == 1

    def test_all_values_are_uppercase_strings(self):
        for name in ZERO_WIDTH_CHARS.values():
            assert name.isupper()
            assert isinstance(name, str)
