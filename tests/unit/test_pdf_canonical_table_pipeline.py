from __future__ import annotations

import asyncio

import pytest

from docmirror.evidence.plane import EvidencePlaneBuilder
from docmirror.input.extraction.extractor import CoreExtractor
from docmirror.output.community_bundle import project_community_bundle


def _write_vector_table_pdf(path) -> None:
    canvas_mod = pytest.importorskip("reportlab.pdfgen.canvas")
    canvas = canvas_mod.Canvas(str(path), pagesize=(300, 220))
    xs = [30, 120, 270]
    ys = [180, 150, 120]
    for x in xs:
        canvas.line(x, ys[-1], x, ys[0])
    for y in ys:
        canvas.line(xs[0], y, xs[-1], y)
    canvas.drawString(40, 160, "Name")
    canvas.drawString(130, 160, "Alice")
    canvas.drawString(40, 130, "Status")
    canvas.drawString(130, 130, "Active")
    canvas.save()


def test_native_pdf_table_evidence_survives_into_parse_result(tmp_path) -> None:
    pytest.importorskip("fitz")
    path = tmp_path / "vector-table.pdf"
    _write_vector_table_pdf(path)

    plane = EvidencePlaneBuilder().build(path)
    candidates = plane.evidence.indexes["table_candidates"]

    assert plane.counts["vector_atoms"] > 0
    assert plane.counts["table_candidates"] == 1
    assert candidates[0]["geometry"]["cell_bboxes"][0][0]
    assert candidates[0]["geometry"]["cell_token_ids"][0][0]
    assert plane.evidence.vector_atoms[0].metadata["geometry"]["items"]

    result = asyncio.run(CoreExtractor().extract_parse_result(path))

    assert result.total_tables == 1
    assert result.parser_info.table_engine == "pymupdf_native"
    assert result.evidence_plane is not None
    assert len(result.evidence_plane.evidence.vector_atoms) == plane.counts["vector_atoms"]
    assert result.document_flow is not None
    assert any(node.type == "physical_table" for node in result.document_flow.nodes)

    mirror = result.to_mirror_json_vnext(source_filename=str(path))
    assert len(mirror["evidence"]["vector_atoms"]) == plane.counts["vector_atoms"]
    assert mirror["evidence"]["indexes"]["table_candidates"]

    table = result.pages[0].tables[0]
    table_token_ids = {token_id for row in table.rows for cell in row.cells for token_id in cell.token_ids}
    body_token_ids = {token_id for text in result.pages[0].texts for token_id in text.evidence_ids}
    assert table_token_ids
    assert not table_token_ids & body_token_ids

    markdown = project_community_bundle(result, document_id="doc_vector").render_markdown()
    assert "|" in markdown
    assert "<table>" not in markdown
    assert markdown.count("Alice") == 1
    assert markdown.count("Active") == 1


def test_missing_table_reconstruction_is_not_reported_as_ready(tmp_path, monkeypatch) -> None:
    pytest.importorskip("fitz")
    path = tmp_path / "vector-table.pdf"
    _write_vector_table_pdf(path)
    monkeypatch.setattr("docmirror.input.extraction.extractor._native_table_blocks", lambda *_a, **_kw: [])

    result = asyncio.run(CoreExtractor().extract_parse_result(path))

    assert result.status.value == "partial"
    assert "native_table_evidence_not_reconstructed" in result.parser_info.warnings
    gate = result.parser_info.structure["table_reconstruction_gate"]
    assert gate["applicable"] is True
    assert gate["passed"] is False
