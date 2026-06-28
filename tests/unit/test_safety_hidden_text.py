# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for HiddenTextDetector (GA1.0-ODL-04)."""

from __future__ import annotations

import pytest

from docmirror.security.safety.hidden_text import HiddenTextDetector, HiddenTextFlag

pytestmark = [pytest.mark.tier_unit]


class TestHiddenTextDetector:
    """Suite of tests for invisible/hidden text detection."""

    def make_block(self, **overrides) -> dict:
        """Helper: create a text block dict with sensible defaults."""
        block = {
            "block_id": "b0",
            "content": "visible text",
            "text_opacity": 1.0,
            "rendering_mode": 0,
            "font_size": 12.0,
            "bbox": [0, 0, 100, 20],
        }
        block.update(overrides)
        return block

    # ── Detection ──────────────────────────────────────────────────────

    def test_detect_returns_empty_for_visible_blocks(self):
        detector = HiddenTextDetector()
        blocks = [self.make_block(), self.make_block(block_id="b1")]
        flags = detector.detect(blocks)
        assert flags == []

    def test_detect_zero_opacity(self):
        detector = HiddenTextDetector()
        blocks = [self.make_block(text_opacity=0.0, content="invisible payload")]
        flags = detector.detect(blocks)
        assert len(flags) == 1
        assert flags[0].reason == "zero_opacity"
        assert "invisible payload" in flags[0].content

    def test_detect_near_zero_opacity(self):
        detector = HiddenTextDetector()
        # 0.005 is below threshold of 0.01
        blocks = [self.make_block(text_opacity=0.005)]
        flags = detector.detect(blocks)
        assert len(flags) == 1
        assert flags[0].reason == "zero_opacity"

    def test_detect_rendering_mode_three(self):
        detector = HiddenTextDetector()
        blocks = [self.make_block(rendering_mode=3)]
        flags = detector.detect(blocks)
        assert len(flags) == 1
        assert flags[0].reason == "invisible_rendering_mode"

    def test_detect_zero_font_size(self):
        detector = HiddenTextDetector()
        blocks = [self.make_block(font_size=0.0)]
        flags = detector.detect(blocks)
        assert len(flags) == 1
        assert flags[0].reason == "zero_font_size"

    def test_detect_small_font_size(self):
        detector = HiddenTextDetector()
        # 0.3 is below threshold of 0.5
        blocks = [self.make_block(font_size=0.3)]
        flags = detector.detect(blocks)
        assert len(flags) == 1
        assert flags[0].reason == "zero_font_size"

    def test_detect_empty_content_skipped(self):
        detector = HiddenTextDetector()
        blocks = [self.make_block(content="", text_opacity=0.0)]
        flags = detector.detect(blocks)
        assert flags == []

    def test_detect_whitespace_only_skipped(self):
        detector = HiddenTextDetector()
        blocks = [self.make_block(content="   ", text_opacity=0.0)]
        flags = detector.detect(blocks)
        assert flags == []

    def test_detect_mixed_visible_and_hidden(self):
        detector = HiddenTextDetector()
        blocks = [
            self.make_block(block_id="b0", content="visible title"),
            self.make_block(block_id="b1", content="hidden payload", text_opacity=0.0),
            self.make_block(block_id="b2", content="visible body"),
            self.make_block(block_id="b3", content="also hidden", rendering_mode=3),
        ]
        flags = detector.detect(blocks)
        assert len(flags) == 2
        assert flags[0].block_id == "b1"
        assert flags[1].block_id == "b3"

    def test_detect_bbox_included_in_flag(self):
        detector = HiddenTextDetector()
        blocks = [self.make_block(text_opacity=0.0, bbox=[10, 20, 200, 40])]
        flags = detector.detect(blocks)
        assert len(flags) == 1
        assert flags[0].bbox == [10, 20, 200, 40]

    # ── Sanitise ───────────────────────────────────────────────────────

    def test_sanitize_removes_invisible_blocks(self):
        detector = HiddenTextDetector()
        blocks = [
            self.make_block(block_id="b0", content="visible section"),
            self.make_block(block_id="b1", content="hidden", text_opacity=0.0),
            self.make_block(block_id="b2", content="bottom visible"),
        ]
        visible = detector.sanitize(blocks)
        assert len(visible) == 2
        assert visible[0]["block_id"] == "b0"
        assert visible[1]["block_id"] == "b2"

    def test_sanitize_passthrough_when_all_visible(self):
        detector = HiddenTextDetector()
        blocks = [
            self.make_block(block_id="b0"),
            self.make_block(block_id="b1"),
        ]
        visible = detector.sanitize(blocks)
        assert len(visible) == 2

    def test_sanitize_all_removed(self):
        detector = HiddenTextDetector()
        blocks = [
            self.make_block(content="hidden a", font_size=0.1),
            self.make_block(content="hidden b", text_opacity=0.0),
        ]
        visible = detector.sanitize(blocks)
        assert visible == []

    # ── Edge cases ─────────────────────────────────────────────────────

    def test_empty_block_list(self):
        detector = HiddenTextDetector()
        assert detector.detect([]) == []
        assert detector.sanitize([]) == []

    def test_block_without_opacity_key_is_visible(self):
        detector = HiddenTextDetector()
        block = {"block_id": "b0", "content": "hello"}  # no text_opacity key
        flags = detector.detect([block])
        assert flags == []

    def test_block_with_none_values(self):
        detector = HiddenTextDetector()
        block = {"block_id": "b0", "content": "test", "text_opacity": None}
        flags = detector.detect([block])
        assert flags == []

    def test_detect_non_default_thresholds(self):
        detector = HiddenTextDetector()
        detector.MIN_OPACITY_THRESHOLD = 0.5  # much more sensitive
        block = self.make_block(text_opacity=0.4)
        flags = detector.detect([block])
        assert len(flags) == 1
        assert flags[0].reason == "zero_opacity"


class TestHiddenTextFlag:
    """HiddenTextFlag data-class behaviour."""

    def test_default_values(self):
        flag = HiddenTextFlag()
        assert flag.block_id == ""
        assert flag.content == ""
        assert flag.reason == ""
        assert flag.bbox is None
        assert flag.confidence == 1.0

    def test_construction(self):
        flag = HiddenTextFlag(
            block_id="b1",
            content="injected",
            reason="zero_opacity",
            bbox=[0.0, 0.0, 100.0, 20.0],
            confidence=0.95,
        )
        assert flag.block_id == "b1"
        assert flag.confidence == 0.95
