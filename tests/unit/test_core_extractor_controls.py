import asyncio
from pathlib import Path
from types import SimpleNamespace

from docmirror.input.entry.options import normalize_parse_control
from docmirror.input.extraction import extractor as extractor_module
from docmirror.input.extraction.extractor import CoreExtractor
from docmirror.input.extraction.page_splitter import DocumentSpreadPlan, PageSplitDecision
from docmirror.models.entities.domain import Block, TextSpan


def _fake_plane():
    pages = [
        SimpleNamespace(
            page_id="page:0001",
            page_index=0,
            page_number=1,
            width=612.0,
            height=792.0,
            content_mode="text",
        ),
        SimpleNamespace(
            page_id="page:0002",
            page_index=1,
            page_number=2,
            width=612.0,
            height=792.0,
            content_mode="text",
        ),
        SimpleNamespace(
            page_id="page:0003",
            page_index=2,
            page_number=3,
            width=612.0,
            height=792.0,
            content_mode="image",
        ),
    ]
    atoms = [
        SimpleNamespace(id="atom:1", page_id="page:0001", text="page one", bbox=[0, 0, 10, 10]),
        SimpleNamespace(id="atom:2", page_id="page:0002", text="native page two", bbox=[0, 0, 20, 10]),
    ]
    return SimpleNamespace(pages=pages, evidence=SimpleNamespace(text_atoms=atoms))


def _ocr_block(text: str, page_number: int) -> Block:
    block_id = f"ocr:{page_number}"
    return Block(
        block_id=block_id,
        block_type="text",
        spans=(TextSpan(text=text, bbox=(0.0, 0.0, 1.0, 1.0)),),
        bbox=(0.0, 0.0, 1.0, 1.0),
        reading_order=0,
        page=page_number,
        raw_content=text,
        evidence_ids=(block_id,),
    )


def test_vnext_extractor_respects_page_selection_and_auto_ocr(monkeypatch):
    import docmirror.evidence.plane as evidence_plane_module

    class FakeEvidencePlaneBuilder:
        def build(self, _path):
            return _fake_plane()

    ocr_calls = []

    def fake_ocr(_file_path, _page_index, page_number, *, start_order=0):
        ocr_calls.append(page_number)
        return [_ocr_block(f"ocr page {page_number}", page_number)]

    monkeypatch.setattr(evidence_plane_module, "EvidencePlaneBuilder", FakeEvidencePlaneBuilder)
    monkeypatch.setattr(extractor_module, "_ocr_blocks_for_pdf_page", fake_ocr)

    control = normalize_parse_control(pages="2-3", ocr="auto")
    result = asyncio.run(
        CoreExtractor().extract(
            Path("sample.pdf"),
            options={"parse_control": control},
        )
    )

    assert [page.page_number for page in result.pages] == [2, 3]
    assert "page one" not in result.full_text
    assert "native page two" in result.full_text
    assert "ocr page 3" in result.full_text
    assert ocr_calls == [3]
    assert result.metadata["selected_pages"] == [2, 3]
    assert result.metadata["ocr_mode"] == "auto"


def test_vnext_extractor_force_ocr_runs_even_with_native_text(monkeypatch):
    import docmirror.evidence.plane as evidence_plane_module

    class FakeEvidencePlaneBuilder:
        def build(self, _path):
            return _fake_plane()

    ocr_calls = []

    def fake_ocr(_file_path, _page_index, page_number, *, start_order=0):
        ocr_calls.append(page_number)
        return [_ocr_block(f"force ocr page {page_number}", page_number)]

    monkeypatch.setattr(evidence_plane_module, "EvidencePlaneBuilder", FakeEvidencePlaneBuilder)
    monkeypatch.setattr(extractor_module, "_ocr_blocks_for_pdf_page", fake_ocr)

    control = normalize_parse_control(pages="2", ocr="force")
    result = asyncio.run(
        CoreExtractor().extract(
            Path("sample.pdf"),
            options={"parse_control": control},
        )
    )

    assert [page.page_number for page in result.pages] == [2]
    assert "native page two" in result.full_text
    assert "force ocr page 2" in result.full_text
    assert ocr_calls == [2]
    assert result.metadata["ocr_mode"] == "force"


def test_vnext_extractor_suppresses_text_owned_by_scanned_table(monkeypatch):
    import docmirror.evidence.plane as evidence_plane_module

    class FakeEvidencePlaneBuilder:
        def build(self, _path):
            return _fake_plane()

    def fake_ocr(_file_path, _page_index, page_number, *, start_order=0):
        return [
            Block(
                block_id=f"ocr:{page_number}:title",
                block_type="text",
                raw_content="表格标题",
                page=page_number,
                evidence_ids=(f"ocr:{page_number}:title",),
            ),
            Block(
                block_id=f"ocr:{page_number}:row0",
                block_type="text",
                raw_content="项目",
                page=page_number,
                evidence_ids=(f"ocr:{page_number}:row0",),
            ),
            Block(
                block_id=f"ocr:{page_number}:row1",
                block_type="text",
                raw_content="货币资金",
                page=page_number,
                evidence_ids=(f"ocr:{page_number}:row1",),
            ),
        ]

    def fake_reconstruct(blocks, *, page_number, page_width, page_height, start_order=0):
        _ = (blocks, page_width, page_height)
        return Block(
            block_id=f"scanned_table:p{page_number:04d}:0000",
            block_type="table",
            page=page_number,
            reading_order=start_order,
            raw_content=[["项目"], ["货币资金"]],
            evidence_ids=(f"ocr:{page_number}:row0", f"ocr:{page_number}:row1"),
        )

    monkeypatch.setattr(evidence_plane_module, "EvidencePlaneBuilder", FakeEvidencePlaneBuilder)
    monkeypatch.setattr(extractor_module, "_ocr_blocks_for_pdf_page", fake_ocr)
    monkeypatch.setattr(extractor_module, "reconstruct_scanned_statement_table", fake_reconstruct)

    control = normalize_parse_control(pages="3", ocr="force")
    result = asyncio.run(CoreExtractor().extract(Path("sample.pdf"), options={"parse_control": control}))

    blocks = list(result.pages[0].blocks)
    assert [block.block_type for block in blocks] == ["text", "table"]
    assert blocks[0].raw_content == "表格标题"
    assert "货币资金" in result.full_text
    assert all(block.raw_content != "项目" for block in blocks if block.block_type == "text")


def test_vnext_extractor_expands_one_physical_page_to_two_logical_pages(monkeypatch):
    import docmirror.evidence.plane as evidence_plane_module

    class FakeEvidencePlaneBuilder:
        def build(self, _path):
            return _fake_plane()

    plan = DocumentSpreadPlan(
        mode="auto",
        decisions={3: PageSplitDecision(should_split=True, confidence=0.98, expected_nonblank_segments=2)},
        logical_starts={1: 1, 2: 2, 3: 3},
        logical_page_count=4,
        confidence=0.98,
    )

    def fake_logical_ocr(_file_path, _page_index, source_page_number, **_kwargs):
        transform = {
            "source_page_number": source_page_number,
            "matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "inverse_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        }
        return [
            extractor_module._OcrLogicalPage(3, 3, 420.0, 594.0, (_ocr_block("logical three", 3),), transform),
            extractor_module._OcrLogicalPage(4, 3, 420.0, 594.0, (_ocr_block("logical four", 4),), transform),
        ]

    monkeypatch.setattr(evidence_plane_module, "EvidencePlaneBuilder", FakeEvidencePlaneBuilder)
    monkeypatch.setattr(extractor_module, "_build_pdf_spread_plan", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(extractor_module, "_probe_document_ocr_rotation", lambda *_args, **_kwargs: 270)
    monkeypatch.setattr(extractor_module, "_ocr_logical_pages_for_pdf_page", fake_logical_ocr)

    control = normalize_parse_control(pages="3", ocr="auto", page_split="auto")
    result = asyncio.run(CoreExtractor().extract(Path("sample.pdf"), options={"parse_control": control}))

    assert [page.page_number for page in result.pages] == [3, 4]
    assert [page.source_page_number for page in result.pages] == [3, 3]
    assert all(page.is_scanned for page in result.pages)
    assert result.metadata["source_page_count"] == 3
    assert result.metadata["logical_page_count"] == 4
    assert result.metadata["selected_source_pages"] == [3]


def test_ocr_orientation_metrics_trigger_probe_for_garbage_and_reward_early_title():
    garbage = [(0, 0, 10, 10, "000000000", None, None, None, 0.9) for _ in range(6)]
    good = [
        (0, 0, 10, 10, "所有者权益变动表", None, None, None, 0.9),
        (0, 0, 10, 10, "实收资本", None, None, None, 0.9),
        (0, 0, 10, 10, "250,000,000.00", None, None, None, 0.9),
    ]

    garbage_metrics = extractor_module._ocr_orientation_metrics(garbage)
    good_metrics = extractor_module._ocr_orientation_metrics(good)

    assert extractor_module._needs_orientation_probe(garbage_metrics) is True
    assert good_metrics["early_keywords"] >= 1
    assert good_metrics["score"] > garbage_metrics["score"]
