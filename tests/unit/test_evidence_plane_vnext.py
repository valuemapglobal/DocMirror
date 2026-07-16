import hashlib

import pytest

from docmirror.evidence.plane import DocumentSource, EvidencePlaneBuilder, _finalize_indexes
from docmirror.geometry.verification.crops import _page_number as verification_source_page_number
from docmirror.models.entities.parse_result import CellValue, PageContent, ParseResult, TableBlock, TableRow, TextBlock
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


def test_table_geometry_is_owned_once_and_covered_cells_do_not_become_atoms():
    geometry = {
        "geometry_source": "unit_grid",
        "coordinate_system": "pdf_points_top_left",
        "row_bands": [
            {"index": 0, "bbox": [0, 0, 100, 20]},
            {"index": 1, "bbox": [0, 20, 100, 40]},
        ],
        "col_bands": [
            {"index": 0, "bbox": [0, 0, 50, 40]},
            {"index": 1, "bbox": [50, 0, 100, 40]},
        ],
        "cell_bboxes": [
            [[0, 0, 100, 20], None],
            [[0, 20, 50, 40], [50, 20, 100, 40]],
        ],
        "cell_geometry_status": [["exact", "derived"], ["exact", "exact"]],
        "cell_geometry_loss_reason": [[None, "covered_by_merged_cell"], [None, None]],
        "cell_evidence_ids": [[["m"], []], [["a"], ["b"]]],
        "cell_token_ids": [[["m"], []], [["a"], ["b"]]],
        "cell_spans": [{"row": 0, "col": 0, "row_span": 1, "col_span": 2, "bbox": [0, 0, 100, 20]}],
    }
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                width=100,
                height=40,
                tables=[
                    TableBlock(
                        table_id="pt_1_0",
                        headers=[],
                        bbox=[0, 0, 100, 40],
                        metadata={"geometry": geometry, "preserve_headers": False},
                        rows=[
                            TableRow(
                                cells=[
                                    CellValue(
                                        text="merged",
                                        bbox=[0, 0, 100, 20],
                                        row_index=0,
                                        col_index=0,
                                        col_span=2,
                                        geometry_status="exact",
                                        evidence_ids=["m"],
                                        token_ids=["m"],
                                    ),
                                    CellValue(
                                        text="",
                                        row_index=0,
                                        col_index=1,
                                        geometry_status="derived",
                                        geometry_loss_reason="covered_by_merged_cell",
                                    ),
                                ]
                            ),
                            TableRow(
                                cells=[
                                    CellValue(text="A", bbox=[0, 20, 50, 40], evidence_ids=["a"], token_ids=["a"]),
                                    CellValue(text="B", bbox=[50, 20, 100, 40], evidence_ids=["b"], token_ids=["b"]),
                                ]
                            ),
                        ],
                    )
                ],
            )
        ]
    )

    mirror = result.to_mirror_json_vnext()
    atoms = [atom for atom in mirror["evidence"]["text_atoms"] if atom["source_kind"] == "parse_result_table_cell"]
    owners = [atom for atom in atoms if atom["metadata"].get("table_geometry_owner")]
    assert len(atoms) == 3
    assert len(owners) == 1
    assert all("cell_bboxes" not in atom["metadata"] for atom in atoms if atom not in owners)
    grid = next(block for block in mirror["blocks"] if block["type"] == "table")["content"]["grid"]
    occupancy = {}
    for cell in grid["cells"]:
        for row in range(cell["row"], cell["row"] + cell["row_span"]):
            for col in range(cell["col"], cell["col"] + cell["col_span"]):
                assert (row, col) not in occupancy
                occupancy[row, col] = cell["id"]
    assert len(occupancy) == 4


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


def test_logical_parse_page_renders_and_verifies_against_source_physical_page(tmp_path):
    canvas_mod = pytest.importorskip("reportlab.pdfgen.canvas")
    pdf_path = tmp_path / "two-source-pages.pdf"
    canvas = canvas_mod.Canvas(str(pdf_path), pagesize=(200, 300))
    canvas.drawString(20, 260, "physical one")
    canvas.showPage()
    canvas.drawString(20, 260, "physical two")
    canvas.save()

    transform = {
        "source_page_number": 2,
        "source_crop_bbox": [0.0, 0.0, 200.0, 150.0],
        "matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        "inverse_matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    }
    result = ParseResult(
        pages=[
            PageContent(
                page_number=3,
                source_page_number=2,
                coordinate_transform=transform,
                page_mode="scanned_ocr",
                width=200,
                height=150,
                texts=[TextBlock(content="logical page three", bbox=[10, 10, 100, 30])],
            )
        ]
    )
    source = DocumentSource(
        value=result,
        kind="parse_result",
        filename=str(pdf_path),
        mime_type="application/pdf",
    )

    plane = EvidencePlaneBuilder().build(source)

    assert plane.pages[0].page_number == 3
    assert plane.pages[0].content_mode == "scanned_ocr"
    assert plane.pages[0].coordinate_transform["source_page_number"] == 2
    rendered = next(atom for atom in plane.evidence.image_atoms if atom.source_kind == "pymupdf_page_render")
    assert rendered.metadata["source_page_number"] == 2
    assert verification_source_page_number({"page_number": 3, "coordinate_transform": transform}) == 2


def test_parse_result_atom_maps_logical_bbox_back_to_source_bbox():
    transform = {
        "source_page_number": 1,
        "source_crop_bbox": [0.0, 0.0, 200.0, 100.0],
        "matrix": [[0.0, 1.0, 0.0], [-1.0, 0.0, 200.0], [0.0, 0.0, 1.0]],
        "inverse_matrix": [[0.0, -1.0, 200.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
    }
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                source_page_number=1,
                coordinate_transform=transform,
                page_mode="scanned_ocr",
                width=100,
                height=200,
                texts=[TextBlock(content="text", bbox=[10.0, 20.0, 30.0, 40.0], confidence=0.71)],
            )
        ]
    )

    plane = EvidencePlaneBuilder().build(result)
    atom = plane.evidence.text_atoms[0]

    assert atom.coordinate_transform == transform
    assert atom.source_bbox == pytest.approx([160.0, 10.0, 180.0, 30.0])
    assert atom.metadata["source_page_number"] == 1
    assert atom.metadata["logical_page_number"] == 1
    assert atom.confidence == pytest.approx(0.71)


def test_mirror_source_uses_real_sha256_and_page_background_reference(tmp_path):
    canvas_mod = pytest.importorskip("reportlab.pdfgen.canvas")
    pdf_path = tmp_path / "scan.pdf"
    canvas = canvas_mod.Canvas(str(pdf_path), pagesize=(200, 300))
    canvas.drawString(20, 260, "source")
    canvas.save()
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                page_mode="scanned_ocr",
                width=200,
                height=300,
                texts=[TextBlock(content="source", bbox=[20, 30, 80, 50], confidence=0.9)],
            )
        ]
    )

    mirror = result.to_mirror_json_vnext(source_filename=str(pdf_path))

    assert mirror["source"]["sha256"] == hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    background = next(
        atom for atom in mirror["evidence"]["image_atoms"] if atom["metadata"]["role"] == "page_background"
    )
    assert background["bbox"] == [0.0, 0.0, 200.0, 300.0]
    assert background["metadata"]["pixel_width"] > 0
    assert background["metadata"]["pixel_height"] > 0
    assert mirror["evidence"]["visual_atoms"] == []


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
