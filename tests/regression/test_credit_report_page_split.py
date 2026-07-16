from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from docmirror.input.bridge.parse_result_bridge import ParseResultBridge
from docmirror.input.entry.options import normalize_parse_control
from docmirror.input.extraction.extractor import CoreExtractor

_FIXTURE = Path("tests/fixtures/credit_report/洪晓鑫征信报告2025.11.05.pdf")

pytestmark = pytest.mark.slow


@pytest.mark.skipif(
    os.environ.get("DOCMIRROR_RUN_REAL_OCR") != "1",
    reason="set DOCMIRROR_RUN_REAL_OCR=1 to run real scanned PDF OCR gate",
)
@pytest.mark.skipif(not _FIXTURE.exists(), reason="credit report fixture is not available")
def test_real_credit_report_rotated_spreads_expand_to_eleven_logical_pages():
    control = normalize_parse_control(ocr="auto", page_split="auto", cache_policy="off")
    result = asyncio.run(CoreExtractor().extract(_FIXTURE, options={"parse_control": control}))

    assert result.metadata["source_page_count"] == 6
    assert result.metadata["logical_page_count"] == 11
    assert [page.page_number for page in result.pages] == list(range(1, 12))
    assert [page.source_page_number for page in result.pages] == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6]
    assert all(page.is_scanned for page in result.pages)
    assert all(page.width < page.height for page in result.pages)
    assert all(page.coordinate_transform.get("inverse_matrix") for page in result.pages)
    assert "个人信用报告" in result.full_text
    assert "第11页" in result.full_text.replace(" ", "")

    table_pages = {
        page.page_number for page in result.pages if any(block.block_type == "table" for block in page.blocks)
    }
    assert table_pages == set(range(1, 10))
    assert all(not any(block.block_type == "table" for block in page.blocks) for page in result.pages[9:])

    parse_result = ParseResultBridge.from_base_result(result)
    assert len(parse_result.raw_text) >= 10_000
    assert len(parse_result.full_text) >= 9_000
    mirror = parse_result.to_mirror_json_vnext(source_filename=str(_FIXTURE.resolve()))
    assert mirror["mirror"]["schema_version"] == "1.0.1"
    assert mirror["source"]["page_count"] == 6
    assert len(mirror["source"]["sha256"]) == 64
    assert not mirror["source"]["sha256"].startswith("fast:")
    assert mirror["document"]["content_mode"] == "scanned_ocr"
    assert mirror["document"]["title"]["text"] == "个人信用报告"
    assert mirror["source"]["provenance"]["parser_info"]["extraction_method"] == "ocr"
    assert len(mirror["evidence"]["image_atoms"]) == 11
    assert mirror["evidence"]["visual_atoms"] == []
    source_refs = [
        source_ref for atom in mirror["evidence"]["text_atoms"] for source_ref in atom.get("source_refs") or []
    ]
    assert len(source_refs) >= 1_600
    assert len(source_refs) == len(set(source_refs))
    table_atoms = [
        atom for atom in mirror["evidence"]["text_atoms"] if atom["source_kind"] == "parse_result_table_cell"
    ]
    assert all(atom.get("text") or atom.get("source_refs") for atom in table_atoms)
    geometry_owners = [atom for atom in table_atoms if atom["metadata"].get("table_geometry_owner")]
    table_blocks = [block for block in mirror["blocks"] if block["type"] == "table"]
    assert len(geometry_owners) == len(table_blocks)
    assert "bank_statement" not in mirror["semantics"]["views"]

    physical_ids = {block["provenance"]["source_table_id"] for block in table_blocks}
    logical_refs = mirror["source"]["provenance"]["logical_tables"]
    referenced_ids = [source_id for item in logical_refs for source_id in item["source_physical_ids"]]
    assert len(physical_ids) == len(table_blocks)
    assert set(referenced_ids) == physical_ids
    assert len(referenced_ids) == len(set(referenced_ids))
    assert not any(
        edge["from"] == edge["to"] for edge in mirror["graph"]["edges"] if edge["type"] in {"same_table", "continues"}
    )
    for block in table_blocks:
        grid = block["content"]["grid"]
        row_count = len(grid["rows"])
        column_count = len(grid["columns"])
        occupancy: set[tuple[int, int]] = set()
        for cell in grid["cells"]:
            assert cell["row"] + cell["row_span"] <= row_count
            assert cell["col"] + cell["col_span"] <= column_count
            for row in range(cell["row"], cell["row"] + cell["row_span"]):
                for col in range(cell["col"], cell["col"] + cell["col_span"]):
                    assert (row, col) not in occupancy
                    occupancy.add((row, col))

    assert len(json.dumps(mirror, ensure_ascii=False, separators=(",", ":")).encode()) <= 5_000_000
    assert len(json.dumps(mirror, ensure_ascii=False, indent=2).encode()) <= 12_000_000
    confidences = [atom["confidence"] for atom in mirror["evidence"]["text_atoms"]]
    assert min(confidences) < 0.8
    assert max(confidences) <= 1.0
    assert mirror["quality"]["overall"]["status"] == "warn"
    gates = {gate["id"]: gate for gate in mirror["quality"]["gates"]}
    assert gates["gate:coordinate_roundtrip"]["status"] == "pass"
    assert gates["gate:scanned_visual_coverage"]["status"] == "pass"
    assert gates["gate:table_structure_coverage"]["status"] in {"pass", "warn"}
    assert gates["gate:table_grid_integrity"]["status"] == "pass"
    assert gates["gate:physical_table_reference_integrity"]["status"] == "pass"
    assert gates["gate:text_source_conservation"]["status"] == "pass"
