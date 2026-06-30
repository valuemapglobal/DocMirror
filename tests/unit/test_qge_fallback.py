"""
QGE (Quality-Gated Extraction) fallback tests.

Tests the ``CoreExtractor._qge_*`` static methods that provide plain-OCR
fallback for image inputs when the primary pipeline extracts too little text.

Test tiers:
  - tier_unit: Unit tests for quality assessment + merge logic (no OCR deps)
  - tier_smoke: Integration tests that call RapidOCR (requires ocr extra)
"""

from __future__ import annotations

import pytest

from docmirror.input.extraction.extractor import CoreExtractor
from docmirror.models.entities.physical import Block, PageLayout

pytestmark = [pytest.mark.tier_unit]


# ── QGE Quality Assessment Tests ──


class TestQgeAssessQuality:
    """Validate _qge_assess_quality scoring logic."""

    def test_low_quality_empty(self):
        """Empty result -> score=0.0, reason='text_too_sparse'."""
        quality = CoreExtractor._qge_assess_quality([], "")
        assert quality.score == 0.0
        assert quality.reason == "text_too_sparse"
        assert quality.total_text_chars == 0
        assert quality.table_count == 0

    def test_low_quality_sparse_text(self):
        """Very little text and no structure -> score < 0.3."""
        pages = [
            PageLayout(
                page_number=1,
                width=100,
                height=100,
                blocks=(Block(block_id="t1", block_type="text", raw_content="hello"),),
            )
        ]
        quality = CoreExtractor._qge_assess_quality(pages, "hello")
        assert quality.score < 0.3
        assert quality.reason is not None

    def test_high_quality_rich_text(self):
        """Plenty of text blocks -> score >= 0.3, no fallback needed."""
        blocks = tuple(Block(block_id=f"t{i}", block_type="text", raw_content="A" * 100) for i in range(10))
        pages = [PageLayout(page_number=1, width=100, height=100, blocks=blocks)]
        quality = CoreExtractor._qge_assess_quality(pages, "A" * 1000)
        assert quality.score >= 0.3
        assert quality.reason is None

    def test_text_blob_penalty(self):
        """Text crammed into very few blocks -> blob penalty lowers score."""
        blocks = tuple(Block(block_id=f"t{i}", block_type="text", raw_content="A" * 800) for i in range(2))
        pages = [PageLayout(page_number=1, width=100, height=100, blocks=blocks)]
        quality = CoreExtractor._qge_assess_quality(pages, "A" * 1600)
        # 1600 chars in 2 blocks = 800 chars/block -> blob penalty applied
        # reason is "no_structure" (few blocks + penalized text_score)
        assert quality.score < 0.3
        assert quality.reason is not None

    def test_high_quality_with_table(self):
        """Few text blocks but a table -> structure_score saves it."""
        pages = [
            PageLayout(
                page_number=1,
                width=100,
                height=100,
                blocks=(Block(block_id="t1", block_type="table", raw_content=[["h1", "h2"], ["v1", "v2"]]),),
            )
        ]
        quality = CoreExtractor._qge_assess_quality(pages, "")
        assert quality.score >= 0.3
        assert quality.reason is None

    def test_boundary_text_under_100_chars(self):
        """Under 100 chars with no structure -> text_too_sparse."""
        blocks = tuple(Block(block_id=f"b{i}", block_type="text", raw_content="short") for i in range(2))
        pages = [PageLayout(page_number=1, width=100, height=100, blocks=blocks)]
        quality = CoreExtractor._qge_assess_quality(pages, "short")
        assert quality.reason == "text_too_sparse"


# ── QGE Merge Logic Tests ──


class TestQgeMergeResults:
    """Validate _qge_merge_results merging strategy."""

    def test_empty_ocr_blocks_noop(self):
        """Passing empty OCR blocks -> no change."""
        pages = [PageLayout(page_number=1, width=100, height=100, blocks=())]
        result_pages, result_text, tc, tb = CoreExtractor._qge_merge_results(pages, "", [])
        assert len(result_pages[0].blocks) == 0
        assert result_text == ""

    def test_merge_into_empty_page(self):
        """OCR blocks merged into a page with no blocks."""
        pages = [PageLayout(page_number=1, width=100, height=100, blocks=())]
        ocr_blocks = [
            Block(block_id="qge_0", block_type="text", raw_content="line1"),
            Block(block_id="qge_1", block_type="text", raw_content="line2"),
        ]
        result_pages, result_text, tc, tb = CoreExtractor._qge_merge_results(pages, "", ocr_blocks)
        assert len(result_pages[0].blocks) == 2
        assert "line1" in result_text
        assert "line2" in result_text

    def test_merge_preserves_tables(self):
        """Existing table blocks are preserved, only text blocks replaced."""
        pages = [
            PageLayout(
                page_number=1,
                width=100,
                height=100,
                blocks=(
                    Block(block_id="tb1", block_type="table", raw_content=[["header"]]),
                    Block(block_id="tx1", block_type="text", raw_content="old"),
                ),
            )
        ]
        ocr_blocks = [
            Block(block_id="qge_0", block_type="text", raw_content="new text"),
        ]
        result_pages, result_text, tc, tb = CoreExtractor._qge_merge_results(pages, "", ocr_blocks)
        blocks = result_pages[0].blocks
        table_blocks = [b for b in blocks if b.block_type == "table"]
        text_blocks = [b for b in blocks if b.block_type == "text"]
        assert len(table_blocks) == 1
        assert len(text_blocks) == 1
        assert text_blocks[0].raw_content == "new text"

    def test_skip_when_sufficient_text(self):
        """Page with 3+ text blocks -> merge skipped."""
        pages = [
            PageLayout(
                page_number=1,
                width=100,
                height=100,
                blocks=tuple(Block(block_id=f"t{i}", block_type="text", raw_content=f"text{i}") for i in range(3)),
            )
        ]
        ocr_blocks = [
            Block(block_id="qge_0", block_type="text", raw_content="new"),
        ]
        result_pages, result_text, tc, tb = CoreExtractor._qge_merge_results(pages, "existing text", ocr_blocks)
        assert "new" not in result_text
        assert tc == 0 and tb == 0

    def test_full_text_rebuilt(self):
        """full_text is rebuilt to include OCR text."""
        pages = [PageLayout(page_number=1, width=100, height=100, blocks=())]
        ocr_blocks = [
            Block(block_id="qge_0", block_type="text", raw_content="ocr result"),
        ]
        _, result_text, _, _ = CoreExtractor._qge_merge_results(pages, "original", ocr_blocks)
        assert "original" in result_text
        assert "ocr result" in result_text


# ── QGE Plain OCR Fallback (integration) ──


@pytest.mark.tier_smoke
class TestQgePlainOcrFallback:
    """Integration tests that call RapidOCR with a real image.

    Requires ``pip install \"docmirror[ocr]\"`` and a test fixture image.
    """

    def test_non_image_path_returns_empty(self):
        """Calling with a non-image path (.py) -> empty list."""
        import pathlib

        blocks, tokens = CoreExtractor._qge_plain_ocr_fallback(pathlib.Path("dummy.txt"))
        assert blocks == []
        assert tokens == []

    def test_fallback_on_image_uses_ocr_words(self, tmp_path, monkeypatch):
        """Image fallback converts OCR words into text blocks and token evidence."""

        class _FakeOcrEngine:
            def detect_image_words(self, _img):
                return [
                    (10, 10, 60, 22, "银行", 0.96),
                    (70, 10, 130, 22, "余额", 0.95),
                    (10, 40, 80, 52, "汇款", 0.94),
                ]

        fixture = tmp_path / "scan.png"
        fixture.write_bytes(b"synthetic")
        monkeypatch.setattr("cv2.imread", lambda _path: object())
        monkeypatch.setattr(CoreExtractor, "_preprocess_ocr_image", staticmethod(lambda img: img))
        monkeypatch.setattr("docmirror.ocr.vision.rapidocr_engine.get_ocr_engine", lambda: _FakeOcrEngine())

        blocks, tokens = CoreExtractor._qge_plain_ocr_fallback(fixture)

        assert len(blocks) > 0
        assert len(tokens) > 0
        all_text = " ".join(b.raw_content for b in blocks if isinstance(b.raw_content, str))
        assert "银行" in all_text
        assert tokens[0]["source"] == "qge_fallback"
