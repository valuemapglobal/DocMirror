"""Unit tests for parallel layout analysis (Phase 1 page-concurrency)."""

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def two_page_pdf_path():
    """Create a minimal 2-page PDF on disk for layout analysis."""
    try:
        import fitz
    except ImportError:
        pytest.skip("PyMuPDF (fitz) not installed")
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    path = tmp.name
    try:
        doc = fitz.open()
        doc.insert_page(0, text="Page one")
        doc.insert_page(1, text="Page two")
        doc.save(path)
        doc.close()
        yield path
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


class TestAnalyzeDocumentLayoutParallel:
    """Test analyze_document_layout_parallel returns correct structure."""

    def test_returns_one_layout_per_page(self, two_page_pdf_path):
        from docmirror.core.layout.layout_analysis import (
            analyze_document_layout_parallel,
            analyze_document_layout,
        )
        path = str(Path(two_page_pdf_path).resolve())
        layouts = analyze_document_layout_parallel(path, num_pages=2, max_workers=2)
        assert len(layouts) == 2
        assert layouts[0].page_index == 0
        assert layouts[1].page_index == 1
        assert layouts[0].width > 0 and layouts[0].height > 0
        assert layouts[1].width > 0 and layouts[1].height > 0

    def test_parallel_matches_sequential_for_two_pages(self, two_page_pdf_path):
        from docmirror.core.layout.layout_analysis import (
            analyze_document_layout_parallel,
            analyze_document_layout,
        )
        import fitz
        path = str(Path(two_page_pdf_path).resolve())
        parallel_layouts = analyze_document_layout_parallel(path, num_pages=2, max_workers=2)
        doc = fitz.open(path)
        try:
            sequential_layouts = analyze_document_layout(doc)
        finally:
            doc.close()
        # Same number of regions and basic shape per page
        assert len(parallel_layouts) == len(sequential_layouts)
        for pa, se in zip(parallel_layouts, sequential_layouts):
            assert pa.page_index == se.page_index
            assert abs(pa.width - se.width) < 1e-6
            assert abs(pa.height - se.height) < 1e-6
            assert len(pa.regions) == len(se.regions)

    def test_single_page_uses_in_process_fallback(self, two_page_pdf_path):
        from docmirror.core.layout.layout_analysis import analyze_document_layout_parallel
        path = str(Path(two_page_pdf_path).resolve())
        layouts = analyze_document_layout_parallel(path, num_pages=1, max_workers=4)
        assert len(layouts) == 1
        assert layouts[0].page_index == 0

    def test_max_workers_one_uses_sequential_path(self, two_page_pdf_path):
        from docmirror.core.layout.layout_analysis import analyze_document_layout_parallel
        path = str(Path(two_page_pdf_path).resolve())
        layouts = analyze_document_layout_parallel(path, num_pages=2, max_workers=1)
        assert len(layouts) == 2
        assert [l.page_index for l in layouts] == [0, 1]
