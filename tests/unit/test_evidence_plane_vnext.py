import pytest

from docmirror.evidence.plane import DocumentSource, EvidencePlaneBuilder, _finalize_indexes
from docmirror.models.mirror.core import MirrorCoreVNext
from docmirror.models.mirror.vnext import EvidenceAtom, EvidenceStore
from tests.unit.test_mirror_json_vnext import _sample_parse_result


def test_evidence_plane_from_parse_result_collects_atoms_and_indexes():
    plane = EvidencePlaneBuilder().build(_sample_parse_result())

    assert plane.source.input_kind == "parse_result"
    assert plane.counts["pages"] == 1
    assert plane.counts["text_atoms"] >= 10
    assert "page:0001" in plane.evidence.indexes["by_page"]
    assert "parse_result_table_cell" in plane.evidence.indexes["by_source"]
    assert plane.diagnostics_entry()["stage"] == "evidence_plane_builder"


def test_document_source_from_path_records_file_metadata(tmp_path):
    path = tmp_path / "sample.pdf"
    path.write_bytes(b"%PDF-1.4\n%%EOF\n")

    source = DocumentSource.from_any(path)

    assert source.kind == "pdf"
    assert source.filename == "sample.pdf"
    assert source.mime_type == "application/pdf"
    assert source.size_bytes == path.stat().st_size
    assert len(source.sha256) == 64


def test_evidence_plane_from_pdf_native_text_and_core_evidence_only(tmp_path):
    canvas_mod = pytest.importorskip("reportlab.pdfgen.canvas")
    pdf_path = tmp_path / "native.pdf"
    canvas = canvas_mod.Canvas(str(pdf_path), pagesize=(200, 200))
    canvas.drawString(36, 128, "Hello Evidence")
    canvas.line(20, 100, 180, 100)
    canvas.save()

    plane = EvidencePlaneBuilder().build(pdf_path)

    assert plane.source.input_kind == "pdf"
    assert plane.counts["pages"] == 1
    assert any(atom.text == "Hello" for atom in plane.evidence.text_atoms)
    assert any(atom.text == "Evidence" for atom in plane.evidence.text_atoms)
    assert plane.pages[0].evidence_ids
    assert "pymupdf" in plane.source.provenance.get("pdf_intake_backends", [])
    assert "pypdf" in plane.source.provenance.get("pdf_intake_backends", [])

    mirror = MirrorCoreVNext().process(pdf_path).to_dict()
    assert mirror["mirror"]["schema"] == "docmirror.mirror_json"
    assert mirror["source"]["input_kind"] == "pdf"
    assert any(block["type"] == "paragraph" and "Hello Evidence" in block["text"] for block in mirror["blocks"])
    assert mirror["diagnostics"]["pipeline"][1]["stage"] == "page_topology_segmentation"
    assert mirror["diagnostics"]["pipeline"][1]["status"] == "ok"


def test_evidence_plane_records_source_bbox_and_coordinate_transform_for_rotated_pdf(tmp_path):
    pytest.importorskip("fitz")
    canvas_mod = pytest.importorskip("reportlab.pdfgen.canvas")

    pdf_path = tmp_path / "rotated.pdf"
    canvas = canvas_mod.Canvas(str(pdf_path), pagesize=(200, 300))
    canvas.drawString(36, 220, "Rotated Evidence")
    canvas.save()

    import fitz

    doc = fitz.open(pdf_path)
    doc[0].set_rotation(90)
    rotated_path = tmp_path / "rotated_saved.pdf"
    doc.save(rotated_path)
    doc.close()

    plane = EvidencePlaneBuilder().build(rotated_path)
    atom = next(atom for atom in plane.evidence.text_atoms if atom.text == "Rotated")

    assert plane.pages[0].coordinate_transform["source_rotation"] == 90
    assert atom.bbox
    assert atom.source_bbox
    assert atom.coordinate_transform
    assert atom.coordinate_transform["source_rotation"] == 90
    assert atom.coordinate_transform["matrix"] != [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]

    mirror = MirrorCoreVNext().process(rotated_path).to_dict()
    assert mirror["pages"][0]["coordinate_transform"]["source_rotation"] == 90


def test_evidence_plane_indexes_same_visual_text_candidates():
    evidence = EvidenceStore(
        text_atoms=[
            EvidenceAtom(
                id="ev:0001:text:000001",
                kind="text_token",
                source_kind="pdf_native",
                page_id="page:0001",
                text="交易日期",
                bbox=[10.0, 10.0, 50.0, 20.0],
            ),
            EvidenceAtom(
                id="ev:0001:text:000002",
                kind="text_token",
                source_kind="metadata_ocr_token",
                page_id="page:0001",
                text="交易日期",
                bbox=[10.0, 10.0, 50.0, 20.0],
            ),
        ]
    )

    _finalize_indexes(evidence)

    candidates = evidence.indexes["same_visual_text_candidates"]
    assert candidates == [
        {
            "type": "same_visual_text_candidate",
            "native_id": "ev:0001:text:000001",
            "ocr_id": "ev:0001:text:000002",
            "page_id": "page:0001",
            "iou": 1.0,
            "dedupe_action": "prefer_native",
        }
    ]
    assert evidence.text_atoms[0].metadata["same_visual_text_candidate_ids"] == ["ev:0001:text:000002"]
    assert evidence.indexes["dedup_prefer_native_text_ids"] == ["ev:0001:text:000001"]
    assert evidence.indexes["dedup_suppressed_ocr_text_ids"] == ["ev:0001:text:000002"]


def test_evidence_plane_pdf_merges_pypdf_metadata_sidecar(tmp_path):
    pytest.importorskip("pypdf")
    canvas_mod = pytest.importorskip("reportlab.pdfgen.canvas")

    pdf_path = tmp_path / "metadata.pdf"
    canvas = canvas_mod.Canvas(str(pdf_path), pagesize=(200, 200))
    canvas.setTitle("Evidence Title")
    canvas.drawString(36, 128, "Metadata Evidence")
    canvas.bookmarkPage("page_one")
    canvas.addOutlineEntry("Page One", "page_one")
    canvas.save()

    plane = EvidencePlaneBuilder().build(pdf_path)

    assert plane.source.provenance["pdf_metadata"]["Title"] == "Evidence Title"
    assert plane.source.provenance["pdf_outline"][0]["title"] == "Page One"
    assert any(atom.source_kind == "pdf_native" for atom in plane.evidence.text_atoms)
