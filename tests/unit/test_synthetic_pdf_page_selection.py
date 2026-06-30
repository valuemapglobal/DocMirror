import pytest

from docmirror.input.entry.options import parse_page_selection


def test_synthetic_large_pdf_layout_honors_selected_pages(tmp_path):
    fitz = pytest.importorskip("fitz")

    pdf_path = tmp_path / "large.pdf"
    doc = fitz.open()
    for idx in range(120):
        page = doc.new_page()
        page.insert_text((72, 72), f"page {idx + 1}")
    doc.save(pdf_path)
    doc.close()

    from docmirror.layout.segment.layout_analysis import analyze_document_layout

    opened = fitz.open(pdf_path)
    try:
        selected = parse_page_selection("5,60,120").resolve(len(opened))
        layouts = analyze_document_layout(opened, page_indices=selected)
    finally:
        opened.close()

    assert [layout.page_index for layout in layouts] == [4, 59, 119]
