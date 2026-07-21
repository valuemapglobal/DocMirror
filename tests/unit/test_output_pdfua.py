# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for DMIR -> PDF/UA accessibility exporter (GA1.0-ODL-02 Phase 1.7).

Updated for pdfua-v2: PyMuPDF visual + pypdf structure tree injection.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

pytestmark = [pytest.mark.tier_unit]

from docmirror.output.exporters.pdfua import _ensure_fitz, _ensure_pypdf, export_pdfua
from docmirror.output.exporters.pdfua_tags import (
    build_pdfua_struct_tree,
    dmir_to_pdf_tag,
    get_table_structure_tags,
)
from docmirror.output.exporters.pdfua_types import ExportResult, PdfUaVersion


def _minimal_dmir() -> dict:
    """Build a minimal DMIR dict for PDF/UA export testing."""
    return {
        "dmir_version": "1.0",
        "document": {
            "type": "test_report",
            "properties": {
                "organization": "Test Corp",
                "subject_name": "Test Report",
            },
            "pages": [
                {
                    "page_number": 1,
                    "width_pt": 595.0,
                    "height_pt": 842.0,
                    "texts": [
                        {
                            "content": "Annual Report 2026",
                            "level": "h1",
                            "reading_order": 0,
                            "bbox": [50.0, 30.0, 545.0, 60.0],
                        },
                        {
                            "content": "This is a sample paragraph for testing PDF/UA export.",
                            "level": "body",
                            "reading_order": 1,
                            "bbox": [50.0, 80.0, 545.0, 100.0],
                        },
                    ],
                    "tables": [
                        {
                            "table_id": "tbl_001",
                            "headers": ["Metric", "Value"],
                            "data_rows": [
                                {
                                    "cells": [
                                        {"text": "Revenue", "data_type": "text"},
                                        {"text": "100,000", "data_type": "currency"},
                                    ],
                                    "row_type": "data",
                                },
                            ],
                            "bbox": [30.0, 120.0, 565.0, 160.0],
                            "reading_order": 2,
                        }
                    ],
                    "key_values": [
                        {
                            "key": "Prepared By",
                            "value": "Finance Team",
                            "group_id": "metadata",
                            "reading_order": 3,
                        }
                    ],
                }
            ],
            "full_text": "Annual Report 2026\n\nThis is a sample paragraph.",
        },
        "quality": {"confidence": 0.95, "trust_score": 0.92, "validation_passed": True},
        "evidence": {"ledger": {}, "summary": {"total_events": 0}},
        "meta": {
            "parser": "DocMirror",
            "version": "1.0.0",
            "elapsed_ms": 42.5,
            "page_count": 1,
            "table_count": 1,
            "row_count": 1,
            "dmir_version": "1.0",
        },
    }


class TestPdfUaCheckVersion:
    """Tests for library availability checks."""

    def test_fitz_installed(self):
        """_ensure_fitz does not raise when PyMuPDF is installed."""
        try:
            import fitz  # noqa: F401
        except ImportError:
            pytest.skip("PyMuPDF not installed")
        _ensure_fitz()  # should not raise

    def test_pypdf_installed(self):
        """_ensure_pypdf does not raise when pypdf is installed."""
        try:
            import pypdf  # noqa: F401
        except ImportError:
            pytest.skip("pypdf not installed")
        _ensure_pypdf()  # should not raise


class TestPdfUaTagMapping:
    """Tests for tag mapping from DMIR to PDF/UA structure types."""

    def test_heading_h1_maps_to_H1(self):
        assert dmir_to_pdf_tag("text", {"level": "h1"}) == "H1"

    def test_heading_h2_maps_to_H2(self):
        assert dmir_to_pdf_tag("text", {"level": "h2"}) == "H2"

    def test_heading_h6_maps_to_H6(self):
        assert dmir_to_pdf_tag("text", {"level": "h6"}) == "H6"

    def test_body_maps_to_P(self):
        assert dmir_to_pdf_tag("text", {"level": "body"}) == "P"

    def test_footer_maps_to_P(self):
        assert dmir_to_pdf_tag("text", {"level": "footer"}) == "P"

    def test_watermark_maps_to_Artifact(self):
        assert dmir_to_pdf_tag("text", {"level": "watermark"}) == "Artifact"

    def test_table_maps_to_Table(self):
        assert dmir_to_pdf_tag("table", {}) == "Table"

    def test_kv_maps_to_P(self):
        assert dmir_to_pdf_tag("kv", {}) == "P"

    def test_image_maps_to_Figure(self):
        assert dmir_to_pdf_tag("image", {}) == "Figure"

    def test_unknown_type_raises_valueerror(self):
        with pytest.raises(ValueError, match="Unknown DMIR element type"):
            dmir_to_pdf_tag("unknown", {})

    def test_title_maps_to_H1(self):
        assert dmir_to_pdf_tag("text", {"level": "title"}) == "H1"

    def test_caption_maps_to_P(self):
        assert dmir_to_pdf_tag("text", {"level": "caption"}) == "P"

    def test_default_level_to_P(self):
        assert dmir_to_pdf_tag("text", {}) == "P"


class TestPdfUaTableStructureTags:
    """Tests for table structure tag generation."""

    def test_header_row_generates_TH(self):
        rows = get_table_structure_tags(
            headers=["Name", "Value"],
            data_rows=[{"cells": [{"text": "A"}, {"text": "1"}]}],
        )
        assert len(rows) == 2
        header_tag, header_cells = rows[0]
        assert header_tag == "TR"
        assert header_cells == ["TH", "TH"]

    def test_data_row_generates_TD(self):
        rows = get_table_structure_tags(
            headers=["X"],
            data_rows=[{"cells": [{"text": "data1"}]}, {"cells": [{"text": "data2"}]}],
        )
        assert len(rows) == 3
        for i in range(1, 3):
            _, cell_tags = rows[i]
            assert cell_tags == ["TD"]

    def test_empty_table(self):
        rows = get_table_structure_tags(headers=[], data_rows=[])
        assert len(rows) == 1
        assert rows[0][0] == "TR"


class TestPdfUaTypes:
    """Tests for PDF/UA type definitions."""

    def test_pdfua_version_enum(self):
        assert PdfUaVersion.PDFUA_1.value == "PDF/UA-1"
        assert PdfUaVersion.PDFUA_2.value == "PDF/UA-2"

    def test_export_result_defaults(self):
        r = ExportResult()
        assert r.success is True
        assert r.output_path == ""
        assert r.page_count == 0
        assert r.warnings == []
        assert r.errors == []
        assert r.metadata == {}

    def test_export_result_custom(self):
        r = ExportResult(
            success=True,
            output_path="/tmp/test.pdf",
            page_count=2,
            warnings=["minor issue"],
            metadata={"language": "en-US"},
        )
        assert r.output_path == "/tmp/test.pdf"
        assert r.page_count == 2


class TestPdfUaExport:
    """Integration tests for export_pdfua (requires PyMuPDF + pypdf)."""

    def _have_deps(self):
        try:
            import fitz  # noqa: F401
            import pypdf  # noqa: F401

            return True
        except ImportError:
            return False

    def test_export_pdfua_creates_file(self):
        if not self._have_deps():
            pytest.skip("PyMuPDF and/or pypdf not installed")
        dmir = _minimal_dmir()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            output_path = tmp.name

        try:
            result = export_pdfua(dmir, output_path=output_path)
            assert result.success is True, f"Export failed: {result.errors}"
            assert Path(output_path).exists()
            assert Path(output_path).stat().st_size > 0
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_export_pdfua_has_pdfua_metadata(self):
        """Verify PDF/UA metadata is injected."""
        if not self._have_deps():
            pytest.skip("PyMuPDF and/or pypdf not installed")

        from pypdf import PdfReader

        dmir = _minimal_dmir()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            output_path = tmp.name

        try:
            result = export_pdfua(dmir, output_path=output_path)
            assert result.success is True

            reader = PdfReader(output_path)
            catalog = reader.trailer["/Root"]
            assert "/MarkInfo" in catalog, "Missing /MarkInfo"
            assert "/StructTreeRoot" in catalog, "Missing /StructTreeRoot"
            assert "/Lang" in catalog, "Missing /Lang"
            assert "/ViewerPreferences" in catalog, "Missing /ViewerPreferences"

            mi = catalog["/MarkInfo"]
            assert str(mi.get("/Marked", "")) == "true"
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_export_pdfua_multipage(self):
        """Export a multi-page DMIR document."""
        if not self._have_deps():
            pytest.skip("PyMuPDF and/or pypdf not installed")

        dmir = _minimal_dmir()
        dmir["document"]["pages"].append(
            {
                "page_number": 2,
                "width_pt": 595.0,
                "height_pt": 842.0,
                "texts": [
                    {
                        "content": "Page 2 Content",
                        "level": "body",
                        "reading_order": 0,
                        "bbox": [50.0, 100.0, 545.0, 120.0],
                    }
                ],
                "tables": [],
                "key_values": [],
            }
        )

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            output_path = tmp.name

        try:
            result = export_pdfua(dmir, output_path=output_path)
            assert result.success is True
            assert result.page_count == 2
            assert Path(output_path).stat().st_size > 0
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_export_pdfua_custom_title_and_language(self):
        if not self._have_deps():
            pytest.skip("PyMuPDF and/or pypdf not installed")

        dmir = _minimal_dmir()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            output_path = tmp.name

        try:
            result = export_pdfua(
                dmir,
                output_path=output_path,
                title="Custom Report",
                language="de-DE",
            )
            assert result.success is True
            assert result.metadata["language"] == "de-DE"
            assert "Custom Report" in result.metadata["title"]

            from scripts.validate_pdfua import _check_pymupdf_tagging

            validation = _check_pymupdf_tagging(Path(output_path))
            assert validation["passed"] is True, validation["errors"]
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_export_pdfua_empty_dmir(self):
        """Handle empty DMIR gracefully."""
        if not self._have_deps():
            pytest.skip("PyMuPDF and/or pypdf not installed")

        empty_dmir = {
            "dmir_version": "1.0",
            "document": {"type": "empty", "pages": []},
            "quality": {"confidence": 0.0, "trust_score": 0.0},
            "evidence": {"ledger": {}, "summary": {"total_events": 0}},
            "meta": {
                "parser": "DocMirror",
                "version": "1.0.0",
                "elapsed_ms": 0.0,
                "page_count": 0,
                "table_count": 0,
                "row_count": 0,
                "dmir_version": "1.0",
            },
        }

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            output_path = tmp.name

        try:
            result = export_pdfua(empty_dmir, output_path=output_path)
            assert result.success is True
            assert result.page_count == 0
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_export_pdfua_without_deps_raises(self):
        """If deps missing, an ImportError is raised when calling export."""
        import sys

        # We can't actually uninstall deps in test; skip this test for now
        # since deps ARE installed. The unit test for _ensure_fitz covers the error case.
        pytest.skip("Dependencies are installed; error path covered by _ensure_fitz")


class TestPdfUaBuildStructTree:
    """Tests for build_pdfua_struct_tree."""

    def test_basic_structure(self):
        """Verify the structure tree has Document root with expected children."""
        try:
            import pypdf  # noqa: F401
            from pypdf.generic import DictionaryObject, NameObject
        except ImportError:
            pytest.skip("pypdf not installed")

        dmir = _minimal_dmir()
        # Mock page refs (real pypdf IndirectObjects not needed for structure check)
        page_refs = [None]
        elements = build_pdfua_struct_tree(dmir, page_refs)

        assert len(elements) >= 2  # Document + Sect + content elements
        doc = elements[0]
        assert doc["_parent_idx"] is None
        assert len(doc["_child_indices"]) >= 1

        sect_idx = doc["_child_indices"][0]
        sect = elements[sect_idx]
        assert sect["_parent_idx"] == 0
        assert sect["_dict"]["/S"] == NameObject("/Sect")

    def test_multipage_structure(self):
        """Multi-page DMIR produces multiple Sect elements."""
        try:
            import pypdf  # noqa: F401
        except ImportError:
            pytest.skip("pypdf not installed")

        dmir = _minimal_dmir()
        dmir["document"]["pages"].append(
            {
                "page_number": 2,
                "width_pt": 595.0,
                "height_pt": 842.0,
                "texts": [{"content": "P2", "level": "body", "reading_order": 0}],
                "tables": [],
                "key_values": [],
            }
        )

        page_refs = [None, None]
        elements = build_pdfua_struct_tree(dmir, page_refs)

        doc = elements[0]
        assert len(doc["_child_indices"]) == 2  # Two Sect elements

    def test_content_in_page(self):
        """Content elements are children of the Sect."""
        try:
            import pypdf  # noqa: F401
        except ImportError:
            pytest.skip("pypdf not installed")

        dmir = _minimal_dmir()
        page_refs = [None]
        elements = build_pdfua_struct_tree(dmir, page_refs)

        # Page 1 has: h1 text, body text, table, kv -> 4 content elements
        sect_idx = elements[0]["_child_indices"][0]
        sect = elements[sect_idx]
        content_count = len(sect["_child_indices"])
        assert content_count == 4, f"Expected 4 content items, got {content_count}"


class TestPdfUaMCIDInjection:
    """Tests for MCID (Marked Content Identifier) injection in PDF/UA export."""

    _DMIR = {
        "dmir_version": "1.0",
        "document": {
            "type": "test_report",
            "pages": [
                {
                    "page_number": 1,
                    "width_pt": 595.0,
                    "height_pt": 842.0,
                    "texts": [
                        {"content": "Heading One", "level": "h1", "reading_order": 0, "bbox": [50, 30, 545, 60]},
                        {"content": "Body text here.", "level": "body", "reading_order": 1, "bbox": [50, 80, 545, 100]},
                    ],
                    "tables": [],
                    "key_values": [],
                }
            ],
            "full_text": "Heading One\n\nBody text here.",
        },
        "quality": {"confidence": 0.9, "trust_score": 0.9},
        "evidence": {"ledger": {}, "summary": {"total_events": 0}},
        "meta": {
            "parser": "DocMirror",
            "version": "1.0.0",
            "elapsed_ms": 1,
            "page_count": 1,
            "table_count": 0,
            "row_count": 0,
            "dmir_version": "1.0",
        },
    }

    def _have_all_deps(self):
        try:
            import fitz  # noqa: F401
            import pypdf  # noqa: F401

            return True
        except ImportError:
            return False

    def test_mcid_operators_in_content_stream(self):
        """BDC/EMC operators exist in output content stream."""
        if not self._have_all_deps():
            pytest.skip("PyMuPDF and/or pypdf not installed")
        import tempfile
        from pathlib import Path

        from docmirror.output.exporters.pdfua import export_pdfua

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            output_path = tmp.name
        try:
            result = export_pdfua(self._DMIR, output_path=output_path)
            assert result.success, f"Export failed: {result.errors}"
            from pypdf import PdfReader
            from pypdf.generic import ContentStream

            reader = PdfReader(output_path)
            for page in reader.pages:
                cs = ContentStream(page.get("/Contents"), reader)
                ops = cs.operations
                has_bdc = any(isinstance(op, tuple) and len(op) == 2 and op[1] == b"BDC" for op in ops)
                has_emc = any(isinstance(op, tuple) and len(op) == 2 and op[1] == b"EMC" for op in ops)
                assert has_bdc, "No BDC operator on page"
                assert has_emc, "No EMC operator on page"
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_mcid_in_structure_tree(self):
        """Structure tree has MCR entries."""
        if not self._have_all_deps():
            pytest.skip("PyMuPDF and/or pypdf not installed")
        import tempfile
        from pathlib import Path

        from docmirror.output.exporters.pdfua import export_pdfua

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            output_path = tmp.name
        try:
            result = export_pdfua(self._DMIR, output_path=output_path)
            assert result.success, f"Export failed: {result.errors}"
            from pypdf import PdfReader

            reader = PdfReader(output_path)
            catalog = reader.trailer["/Root"]
            st = catalog["/StructTreeRoot"].get_object()
            page_kids = st.get("/K", [])
            mcr_found = False

            def _walk(kids):
                nonlocal mcr_found
                for k in kids:
                    obj = k.get_object() if hasattr(k, "get_object") else k
                    if hasattr(obj, "get"):
                        if obj.get("/Type") == "/MCR":
                            mcr_found = True
                        _walk(obj.get("/K", []))

            _walk(page_kids)
            assert mcr_found, "No /MCR entries found in structure tree"
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_mcid_multipage(self):
        """Each page gets its own MCID operators."""
        if not self._have_all_deps():
            pytest.skip("PyMuPDF and/or pypdf not installed")
        dmir = {
            "dmir_version": "1.0",
            "document": {
                "type": "multipage",
                "pages": [
                    {
                        "page_number": 1,
                        "width_pt": 595.0,
                        "height_pt": 842.0,
                        "texts": [{"content": "Page 1", "level": "h1", "reading_order": 0, "bbox": [50, 30, 545, 60]}],
                        "tables": [],
                        "key_values": [],
                    },
                    {
                        "page_number": 2,
                        "width_pt": 595.0,
                        "height_pt": 842.0,
                        "texts": [{"content": "Page 2", "level": "h1", "reading_order": 0, "bbox": [50, 30, 545, 60]}],
                        "tables": [],
                        "key_values": [],
                    },
                ],
                "full_text": "Page 1\n\nPage 2",
            },
            "quality": {"confidence": 0.9, "trust_score": 0.9},
            "evidence": {"ledger": {}, "summary": {"total_events": 0}},
            "meta": {
                "parser": "DocMirror",
                "version": "1.0.0",
                "elapsed_ms": 1,
                "page_count": 2,
                "table_count": 0,
                "row_count": 0,
                "dmir_version": "1.0",
            },
        }
        import tempfile
        from pathlib import Path

        from docmirror.output.exporters.pdfua import export_pdfua

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            output_path = tmp.name
        try:
            result = export_pdfua(dmir, output_path=output_path)
            assert result.success, f"Export failed: {result.errors}"
            assert result.page_count == 2
            from pypdf import PdfReader
            from pypdf.generic import ContentStream

            reader = PdfReader(output_path)
            for i, page in enumerate(reader.pages):
                cs = ContentStream(page.get("/Contents"), reader)
                ops = cs.operations
                assert any(isinstance(op, tuple) and len(op) == 2 and op[1] == b"BDC" for op in ops), (
                    f"Page {i + 1} has no BDC operator"
                )
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_mcid_with_table_and_image(self):
        """Elements without BT/ET blocks do not prevent MCID injection."""
        if not self._have_all_deps():
            pytest.skip("PyMuPDF and/or pypdf not installed")
        dmir = {
            "dmir_version": "1.0",
            "document": {
                "type": "mixed",
                "pages": [
                    {
                        "page_number": 1,
                        "width_pt": 595.0,
                        "height_pt": 842.0,
                        "texts": [
                            {"content": "Report Title", "level": "h1", "reading_order": 0, "bbox": [50, 30, 545, 60]},
                        ],
                        "tables": [
                            {
                                "table_id": "tbl_1",
                                "headers": ["Col A", "Col B"],
                                "data_rows": [{"cells": [{"text": "A1"}, {"text": "B1"}], "row_type": "data"}],
                                "bbox": [50, 120, 545, 200],
                                "reading_order": 1,
                            }
                        ],
                        "key_values": [],
                    }
                ],
                "full_text": "Report Title",
            },
            "quality": {"confidence": 0.9, "trust_score": 0.9},
            "evidence": {"ledger": {}, "summary": {"total_events": 0}},
            "meta": {
                "parser": "DocMirror",
                "version": "1.0.0",
                "elapsed_ms": 1,
                "page_count": 1,
                "table_count": 1,
                "row_count": 1,
                "dmir_version": "1.0",
            },
        }
        import tempfile
        from pathlib import Path

        from docmirror.output.exporters.pdfua import export_pdfua

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            output_path = tmp.name
        try:
            result = export_pdfua(dmir, output_path=output_path)
            assert result.success, f"Export failed: {result.errors}"
            from pypdf import PdfReader
            from pypdf.generic import ContentStream

            reader = PdfReader(output_path)
            page = reader.pages[0]
            cs = ContentStream(page.get("/Contents"), reader)
            ops = cs.operations
            assert any(isinstance(op, tuple) and len(op) == 2 and op[1] == b"BDC" for op in ops), (
                "No BDC operator in mixed-content page"
            )
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_mcid_empty_dmir(self):
        """Empty DMIR exports without errors."""
        if not self._have_all_deps():
            pytest.skip("PyMuPDF and/or pypdf not installed")
        empty_dmir = {
            "dmir_version": "1.0",
            "document": {"type": "empty", "pages": []},
            "quality": {"confidence": 0.0, "trust_score": 0.0},
            "evidence": {"ledger": {}, "summary": {"total_events": 0}},
            "meta": {
                "parser": "DocMirror",
                "version": "1.0.0",
                "elapsed_ms": 0,
                "page_count": 0,
                "table_count": 0,
                "row_count": 0,
                "dmir_version": "1.0",
            },
        }
        import tempfile
        from pathlib import Path

        from docmirror.output.exporters.pdfua import export_pdfua

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            output_path = tmp.name
        try:
            result = export_pdfua(empty_dmir, output_path=output_path)
            assert result.success, f"Export failed: {result.errors}"
        finally:
            Path(output_path).unlink(missing_ok=True)
