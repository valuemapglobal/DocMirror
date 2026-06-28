from pathlib import Path
from tempfile import TemporaryDirectory

from reportlab.pdfgen import canvas as canvas_mod

from docmirror.models.entities.parse_result import LogicalTable, PageContent, ParseResult, TableBlock, TextBlock
from docmirror.models.mirror.vnext import EvidenceAtom
from docmirror.output.mirror import MirrorCoreVNext
from docmirror.structure.evidence_plane import DocumentSource, EvidencePlane, EvidencePlaneBuilder
from docmirror.structure.page_topology import PageTopologyBuilder
from docmirror.structure.reconstructors import ReconstructionContext, RegionReconstructorRegistry
from tests.unit.test_mirror_json_vnext import _sample_parse_result


def test_page_topology_groups_text_atoms_by_line():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                width=200,
                height=200,
                texts=[
                    TextBlock(content="第一行", bbox=[20, 20, 80, 30]),
                    TextBlock(content="第二行", bbox=[20, 60, 80, 70]),
                ],
            )
        ]
    )
    plane = EvidencePlaneBuilder().build(result)
    topology = PageTopologyBuilder(line_gap_tolerance=4).build(plane)

    page = topology.pages[0]
    assert [region.kind for region in page.regions] == ["text", "text"]
    assert [region.reading_order for region in page.regions] == [1, 2]
    assert page.residual_region_ids == []


def test_page_topology_emits_residual_for_empty_page():
    result = ParseResult(pages=[PageContent(page_number=1, width=200, height=200)])
    plane = EvidencePlaneBuilder().build(result)
    topology = PageTopologyBuilder().build(plane)

    page = topology.pages[0]
    assert len(page.regions) == 1
    assert page.regions[0].kind == "residual"
    assert page.regions[0].role in ("empty_page", "scanned_blank_page")
    assert page.regions[0].bbox == [0.0, 0.0, 200.0, 200.0]


def test_page_topology_groups_image_and_vector_atoms_as_visual_regions():
    result = ParseResult(pages=[PageContent(page_number=1, width=200, height=200, texts=[TextBlock(content="文字")])])
    plane = EvidencePlaneBuilder().build(result)
    plane.evidence.image_atoms.append(
        EvidenceAtom(
            id="ev:0001:image:000001",
            kind="embedded_image",
            source_kind="test_image",
            page_id="page:0001",
            bbox=[10.0, 100.0, 50.0, 150.0],
        )
    )
    plane.pages[0].evidence_ids.append("ev:0001:image:000001")
    plane.evidence.vector_atoms.append(
        EvidenceAtom(
            id="ev:0001:vector:000001",
            kind="rectangle",
            source_kind="test_vector",
            page_id="page:0001",
            bbox=[100.0, 100.0, 150.0, 150.0],
        )
    )
    plane.pages[0].evidence_ids.append("ev:0001:vector:000001")

    topology = PageTopologyBuilder().build(plane)

    kinds = [region.kind for region in topology.pages[0].regions]
    assert "image" in kinds
    assert "figure" in kinds
    assert not any(region.kind == "residual" for region in topology.pages[0].regions)

    image_region = next(region for region in topology.pages[0].regions if region.kind == "image")
    figure_region = next(region for region in topology.pages[0].regions if region.kind == "figure")
    image_block = RegionReconstructorRegistry().reconstruct(image_region, _reconstruction_context(plane))
    figure_block = RegionReconstructorRegistry().reconstruct(figure_region, _reconstruction_context(plane))
    assert image_block.type == "artifact"
    assert figure_block.type == "figure"
    assert image_block.evidence_ids == ["ev:0001:image:000001"]
    assert figure_block.evidence_ids == ["ev:0001:vector:000001"]


def test_page_topology_keeps_unknown_visual_atoms_as_residual():
    result = ParseResult(pages=[PageContent(page_number=1, width=200, height=200, texts=[TextBlock(content="文字")])])
    plane = EvidencePlaneBuilder().build(result)
    plane.evidence.visual_atoms.append(
        EvidenceAtom(
            id="ev:0001:visual:000001",
            kind="visual_artifact",
            source_kind="test_visual",
            page_id="page:0001",
            bbox=[10.0, 100.0, 50.0, 150.0],
        )
    )
    plane.pages[0].evidence_ids.append("ev:0001:visual:000001")

    topology = PageTopologyBuilder().build(plane)

    assert [region.kind for region in topology.pages[0].regions] == ["text", "residual"]
    assert topology.pages[0].regions[-1].evidence_ids == ["ev:0001:visual:000001"]


def test_page_topology_promotes_labeled_seal_and_signature_visual_atoms():
    result = ParseResult(pages=[PageContent(page_number=1, width=200, height=200, texts=[TextBlock(content="文字")])])
    plane = EvidencePlaneBuilder().build(result)
    plane.evidence.visual_atoms.extend(
        [
            EvidenceAtom(
                id="ev:0001:visual:000001",
                kind="visual_artifact",
                source_kind="seal_detector",
                page_id="page:0001",
                bbox=[20.0, 100.0, 60.0, 140.0],
            ),
            EvidenceAtom(
                id="ev:0001:visual:000002",
                kind="visual_artifact",
                source_kind="signature_detector",
                page_id="page:0001",
                bbox=[80.0, 100.0, 140.0, 130.0],
            ),
        ]
    )
    plane.pages[0].evidence_ids.extend(["ev:0001:visual:000001", "ev:0001:visual:000002"])

    topology = PageTopologyBuilder().build(plane)
    seal_region = next(region for region in topology.pages[0].regions if region.kind == "seal")
    signature_region = next(region for region in topology.pages[0].regions if region.kind == "signature")

    seal_block = RegionReconstructorRegistry().reconstruct(seal_region, _reconstruction_context(plane))
    signature_block = RegionReconstructorRegistry().reconstruct(signature_region, _reconstruction_context(plane))

    assert topology.diagnostics_entry()["counts"]["seal_regions"] == 1
    assert topology.diagnostics_entry()["counts"]["signature_regions"] == 1
    assert seal_block.type == "artifact"
    assert seal_block.role == "seal"
    assert signature_block.role == "signature"


def test_mirror_core_links_seal_overlay_to_overlapped_block():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                width=200,
                height=200,
                texts=[TextBlock(content="需盖章文本", bbox=[40.0, 80.0, 160.0, 130.0])],
            )
        ]
    )
    plane = EvidencePlaneBuilder().build(result)
    plane.evidence.visual_atoms.append(
        EvidenceAtom(
            id="ev:0001:visual:seal:000001",
            kind="visual_artifact",
            source_kind="seal_detector",
            page_id="page:0001",
            bbox=[60.0, 90.0, 150.0, 125.0],
        )
    )
    plane.pages[0].evidence_ids.append("ev:0001:visual:seal:000001")

    class _EvidenceBuilder:
        def build(self, _source):
            return plane

    mirror = MirrorCoreVNext(evidence_builder=_EvidenceBuilder()).process(DocumentSource.from_any(result)).to_dict()
    seal_block = next(block for block in mirror["blocks"] if block["role"] == "seal")
    paragraph_block = next(block for block in mirror["blocks"] if block["type"] == "paragraph")
    overlay_edges = [edge for edge in mirror["graph"]["edges"] if edge["type"] == "overlays"]

    assert len(overlay_edges) == 1
    assert overlay_edges[0]["from"] == seal_block["id"]
    assert overlay_edges[0]["to"] == paragraph_block["id"]
    assert overlay_edges[0]["metadata"]["overlay_role"] == "seal"


def test_page_topology_groups_table_atoms_as_table_like_region():
    plane = EvidencePlaneBuilder().build(_sample_parse_result())
    topology = PageTopologyBuilder().build(plane)

    table_regions = [region for region in topology.pages[0].regions if region.kind == "table_like"]

    assert len(table_regions) == 1
    assert table_regions[0].role == "table"
    assert table_regions[0].bbox == [42.0, 172.0, 552.0, 742.0]
    assert table_regions[0].diagnostics["grouping"] == "table_metadata_group"
    assert len(table_regions[0].evidence_ids) == 18
    assert not any(
        atom_id in text_region.evidence_ids
        for text_region in topology.pages[0].regions
        if text_region.kind == "text"
        for atom_id in table_regions[0].evidence_ids
    )


def test_page_topology_groups_key_value_atoms_as_document_metadata_region():
    plane = EvidencePlaneBuilder().build(_sample_parse_result())
    topology = PageTopologyBuilder().build(plane)

    kv_regions = [region for region in topology.pages[0].regions if region.role == "document_metadata"]

    assert len(kv_regions) == 1
    assert kv_regions[0].kind == "text"
    assert kv_regions[0].bbox == [72.0, 98.0, 260.0, 136.0]
    assert kv_regions[0].diagnostics["grouping"] == "key_value_metadata_group"
    assert topology.diagnostics_entry()["counts"]["key_value_regions"] == 1


def test_page_topology_promotes_text_level_to_heading_region():
    plane = EvidencePlaneBuilder().build(_sample_parse_result())
    topology = PageTopologyBuilder().build(plane)

    heading_regions = [region for region in topology.pages[0].regions if region.kind == "heading"]

    assert len(heading_regions) == 1
    assert heading_regions[0].role == "title"
    assert heading_regions[0].bbox == [72.0, 60.0, 300.0, 82.0]


def test_page_topology_classifies_geometric_header_and_footer():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                width=200,
                height=200,
                texts=[
                    TextBlock(content="页眉文本", bbox=[20.0, 4.0, 80.0, 12.0]),
                    TextBlock(content="正文文本", bbox=[20.0, 80.0, 80.0, 92.0]),
                    TextBlock(content="页脚文本", bbox=[20.0, 188.0, 80.0, 196.0]),
                ],
            )
        ]
    )
    plane = EvidencePlaneBuilder().build(result)
    topology = PageTopologyBuilder().build(plane)

    header_region = next(region for region in topology.pages[0].regions if region.kind == "header")
    footer_region = next(region for region in topology.pages[0].regions if region.kind == "footer")

    assert header_region.role == "page_header"
    assert footer_region.role == "page_footer"
    assert topology.diagnostics_entry()["counts"]["header_regions"] == 1
    assert topology.diagnostics_entry()["counts"]["footer_regions"] == 1

    header_block = RegionReconstructorRegistry().reconstruct(header_region, _reconstruction_context(plane))
    footer_block = RegionReconstructorRegistry().reconstruct(footer_region, _reconstruction_context(plane))
    assert header_block.type == "header"
    assert footer_block.type == "footer"


def test_mirror_core_suppresses_header_and_footer_from_main_reading_flow():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                width=200,
                height=200,
                texts=[
                    TextBlock(content="页眉文本", bbox=[20.0, 4.0, 80.0, 12.0]),
                    TextBlock(content="正文文本", bbox=[20.0, 80.0, 80.0, 92.0]),
                    TextBlock(content="页脚文本", bbox=[20.0, 188.0, 80.0, 196.0]),
                ],
            )
        ]
    )

    mirror = MirrorCoreVNext().process(result).to_dict()

    header_block = next(block for block in mirror["blocks"] if block["type"] == "header")
    footer_block = next(block for block in mirror["blocks"] if block["type"] == "footer")
    body_block = next(block for block in mirror["blocks"] if block["type"] == "paragraph")
    flow_ids = mirror["graph"]["reading_flows"][0]["node_ids"]

    assert header_block["id"] not in flow_ids
    assert footer_block["id"] not in flow_ids
    assert body_block["id"] in flow_ids
    assert mirror["document"]["root_block_ids"] == [body_block["id"]]
    assert header_block["quality"]["suppressed_from_reading_flow"] is True
    assert footer_block["quality"]["suppressed_from_reading_flow"] is True


def test_page_topology_classifies_toc_entries_and_graph_links():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                width=200,
                height=200,
                texts=[
                    TextBlock(content="目录", bbox=[80.0, 20.0, 120.0, 34.0]),
                    TextBlock(content="一、审计报告 ........ 2", bbox=[20.0, 60.0, 160.0, 74.0]),
                ],
            ),
            PageContent(
                page_number=2,
                width=200,
                height=200,
                texts=[TextBlock(content="一、审计报告", level="h1", bbox=[20.0, 20.0, 120.0, 34.0])],
            ),
        ]
    )
    plane = EvidencePlaneBuilder().build(result)
    topology = PageTopologyBuilder().build(plane)

    toc_title = next(region for region in topology.pages[0].regions if region.role == "toc_title")
    toc_entry = next(region for region in topology.pages[0].regions if region.role == "toc_entry")
    toc_block = RegionReconstructorRegistry().reconstruct(toc_entry, _reconstruction_context(plane))
    mirror = MirrorCoreVNext().process(result).to_dict()
    toc_edges = [edge for edge in mirror["graph"]["edges"] if edge["type"] == "toc_points_to"]
    toc_heading_edges = [
        edge
        for edge in mirror["graph"]["edges"]
        if edge["type"] == "references" and edge["metadata"].get("reference_kind") == "toc_heading"
    ]
    target_heading = next(block for block in mirror["blocks"] if block["type"] == "heading" and block["text"] == "一、审计报告")
    toc_gate = next(gate for gate in mirror["quality"]["gates"] if gate["id"] == "gate:toc_consistency")

    assert toc_title.kind == "heading"
    assert toc_block.type == "toc"
    assert toc_block.content["items"][0]["title"] == "一、审计报告"
    assert toc_block.content["items"][0]["target_page"] == 2
    assert len(toc_edges) == 1
    assert toc_edges[0]["to"] == "page:0002"
    assert toc_edges[0]["metadata"]["relation_kind"] == "toc_section_range"
    assert toc_edges[0]["metadata"]["section_page_range"] == [2, 2]
    assert len(toc_heading_edges) == 1
    assert toc_heading_edges[0]["to"] == target_heading["id"]
    assert toc_heading_edges[0]["metadata"]["relation_kind"] == "toc_heading"
    assert toc_gate["status"] == "pass"
    assert toc_gate["details"]["heading_linked_count"] == 1


def test_page_topology_classifies_text_around_table_by_geometry():
    result = _sample_parse_result()
    result.pages[0].texts.extend(
        [
            TextBlock(content="币种：人民币", bbox=[42.0, 150.0, 120.0, 164.0]),
            TextBlock(content="借方笔数：61 贷方笔数：30", bbox=[42.0, 760.0, 260.0, 776.0]),
        ]
    )
    plane = EvidencePlaneBuilder().build(result)
    topology = PageTopologyBuilder().build(plane)

    preamble = [region for region in topology.pages[0].regions if region.role == "table_preamble"]
    postamble = [region for region in topology.pages[0].regions if region.role in ("table_postamble", "table_summary")]

    assert len(preamble) == 1
    assert len(postamble) == 1
    assert preamble[0].diagnostics["surrounding_table_region_id"].startswith("reg:0001:table")
    assert postamble[0].diagnostics["surrounding_table_region_id"].startswith("reg:0001:table")

    preamble_block = RegionReconstructorRegistry().reconstruct(preamble[0], _reconstruction_context(plane))
    postamble_block = RegionReconstructorRegistry().reconstruct(postamble[0], _reconstruction_context(plane))
    assert preamble_block.type == "paragraph"
    assert preamble_block.role == "table_preamble"
    assert postamble_block.role in ("table_postamble", "table_summary")
    assert "借方笔数" in postamble_block.text


def test_page_topology_classifies_table_footnote_and_links_graph_edge():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                width=200,
                height=200,
                tables=[
                    TableBlock(
                        table_id="pt_1_0",
                        headers=["项目", "金额"],
                        page=1,
                        bbox=[20.0, 40.0, 180.0, 120.0],
                    )
                ],
                texts=[
                    TextBlock(content="注：本表金额单位为人民币", bbox=[20.0, 128.0, 180.0, 142.0]),
                ],
            )
        ]
    )
    plane = EvidencePlaneBuilder().build(result)
    topology = PageTopologyBuilder().build(plane)

    footnote_region = next(region for region in topology.pages[0].regions if region.kind == "footnote")
    footnote_block = RegionReconstructorRegistry().reconstruct(footnote_region, _reconstruction_context(plane))
    mirror = MirrorCoreVNext().process(result).to_dict()
    table_block = next(block for block in mirror["blocks"] if block["type"] == "table")
    mirror_footnote = next(block for block in mirror["blocks"] if block["type"] == "footnote")
    footnote_edges = [edge for edge in mirror["graph"]["edges"] if edge["type"] == "footnote_of"]

    assert footnote_region.role == "table_footnote"
    assert footnote_region.diagnostics["surrounding_table_region_id"].startswith("reg:0001:table")
    assert topology.diagnostics_entry()["counts"]["footnote_regions"] == 1
    assert footnote_block.type == "footnote"
    assert len(footnote_edges) == 1
    assert footnote_edges[0]["from"] == mirror_footnote["id"]
    assert footnote_edges[0]["to"] == table_block["id"]
    assert footnote_edges[0]["metadata"]["relation_kind"] == "table_footnote"


def test_financial_statement_reconstructor_enriches_standard_table_grid():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                width=240,
                height=240,
                tables=[
                    TableBlock(
                        table_id="fs_1",
                        headers=["资产负债表", "附注", "期末余额"],
                        page=1,
                        bbox=[20.0, 40.0, 220.0, 160.0],
                    )
                ],
            )
        ]
    )
    plane = EvidencePlaneBuilder().build(result)
    topology = PageTopologyBuilder().build(plane)
    table_region = next(region for region in topology.pages[0].regions if region.kind == "table_like")

    block = RegionReconstructorRegistry().reconstruct(table_region, _reconstruction_context(plane))

    assert block.type == "table"
    assert block.role == "financial_statement"
    assert block.content["grid"]["columns"][0]["header"] == "资产负债表"
    assert block.content["financial_statement"]["fs_type"] == "资产负债表"
    assert block.quality["financial_statement_detected"] is True
    assert block.provenance["reconstructor"] == "financial_statement_reconstructor"


def test_page_topology_classifies_legal_notice_text():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                width=200,
                height=200,
                texts=[TextBlock(content="声明：本对账单仅供参考", bbox=[20.0, 80.0, 180.0, 96.0])],
            )
        ]
    )
    plane = EvidencePlaneBuilder().build(result)
    topology = PageTopologyBuilder().build(plane)

    notice_region = next(region for region in topology.pages[0].regions if region.role == "legal_notice")
    notice_block = RegionReconstructorRegistry().reconstruct(notice_region, _reconstruction_context(plane))

    assert notice_region.kind == "text"
    assert notice_region.diagnostics["classification"] == "legal_notice"
    assert topology.diagnostics_entry()["counts"]["notice_regions"] == 1
    assert notice_block.type == "paragraph"
    assert notice_block.role == "legal_notice"


def test_page_topology_reports_region_overlap_warnings():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                width=200,
                height=200,
                texts=[TextBlock(content="重叠文本", bbox=[30.0, 90.0, 100.0, 110.0])],
                tables=[
                    TableBlock(
                        table_id="pt_1_0",
                        headers=["项目", "金额"],
                        page=1,
                        bbox=[20.0, 80.0, 180.0, 160.0],
                    )
                ],
            )
        ]
    )
    plane = EvidencePlaneBuilder().build(result)

    topology = PageTopologyBuilder(region_overlap_threshold=0.05).build(plane)

    assert topology.diagnostics_entry()["counts"]["overlap_warnings"] == 1
    assert any(
        region.diagnostics.get("overlap_warnings")
        for region in topology.pages[0].regions
        if region.kind in {"text", "table_like"}
    )


def test_mirror_core_warns_when_regions_overlap():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                width=200,
                height=200,
                texts=[TextBlock(content="重叠文本", bbox=[30.0, 90.0, 100.0, 110.0])],
                tables=[
                    TableBlock(
                        table_id="pt_1_0",
                        headers=["项目", "金额"],
                        page=1,
                        bbox=[20.0, 80.0, 180.0, 160.0],
                    )
                ],
            )
        ]
    )

    mirror = MirrorCoreVNext(topology_builder=PageTopologyBuilder(region_overlap_threshold=0.05)).process(result).to_dict()
    overlap_gate = next(gate for gate in mirror["quality"]["gates"] if gate["id"] == "gate:region_overlap")

    assert overlap_gate["status"] == "warn"
    assert overlap_gate["details"]["overlap_warning_count"] == 1
    assert len(overlap_gate["details"]["overlap_pairs"]) == 1
    assert set(overlap_gate["details"]["target_ids"]) == set(overlap_gate["details"]["overlap_pairs"][0])
    overlap_event = next(event for event in mirror["quality"]["events"] if event["gate_id"] == "gate:region_overlap")
    assert set(overlap_event["target_ids"]) == set(overlap_gate["details"]["target_ids"])
    assert overlap_event["details"]["overlap_pairs"] == overlap_gate["details"]["overlap_pairs"]
    assert any(region["quality"].get("overlap_warnings") for region in mirror["regions"])


def test_region_reconstructor_registry_reconstructs_key_value_group_region():
    plane = EvidencePlaneBuilder().build(_sample_parse_result())
    topology = PageTopologyBuilder().build(plane)
    kv_region = next(region for region in topology.pages[0].regions if region.role == "document_metadata")

    block = RegionReconstructorRegistry().reconstruct(kv_region, _reconstruction_context(plane))

    assert block.type == "key_value_group"
    assert block.provenance["reconstructor"] == "metadata_key_value_group_reconstructor"
    assert [item["key"] for item in block.content["items"]] == ["起始日期", "账户名称"]
    assert block.content["items"][0]["value"]["normalized"] == "2022-06-01"
    assert block.content["items"][0]["value"]["type"] == "date"


def test_region_reconstructor_registry_reconstructs_table_like_region():
    plane = EvidencePlaneBuilder().build(_sample_parse_result())
    topology = PageTopologyBuilder().build(plane)
    table_region = next(region for region in topology.pages[0].regions if region.kind == "table_like")

    block = RegionReconstructorRegistry().reconstruct(table_region, _reconstruction_context(plane))
    grid = block.content["grid"]

    assert block.type == "table"
    assert block.quality["column_count"] == 10
    assert block.quality["row_count"] == 2
    assert [column["header"] for column in grid["columns"]] == [
        "序号",
        "交易日期",
        "交易时间",
        "摘要",
        "凭证种类",
        "借方发生额",
        "贷方发生额",
        "余额",
        "对方账户",
        "对方户名",
    ]
    assert len(grid["cells"]) == 20
    assert grid["cells"][14]["text"] == ""
    assert grid["cells"][16]["text"] == ""
    assert grid["cells"][10]["value"]["type"] == "number"
    assert grid["cells"][11]["value"]["type"] == "date"
    assert grid["cells"][14]["value"]["type"] == "empty"
    assert grid["cells"][15]["value"]["normalized"] == 10.0


def test_mirror_core_document_source_uses_topology_table_reconstructor():
    mirror = MirrorCoreVNext().process(DocumentSource.from_any(_sample_parse_result())).to_dict()
    table_blocks = [block for block in mirror["blocks"] if block["type"] == "table"]
    kv_blocks = [block for block in mirror["blocks"] if block["type"] == "key_value_group"]
    heading_blocks = [block for block in mirror["blocks"] if block["type"] == "heading"]
    fact_predicates = {fact["predicate"] for fact in mirror["semantics"]["facts"]}

    assert mirror["diagnostics"]["pipeline"][1]["stage"] == "page_topology_segmentation"
    assert len(table_blocks) == 1
    assert len(kv_blocks) == 1
    assert len(heading_blocks) == 1
    assert mirror["document"]["title"]["text"] == "江苏银行对公账户对账单"
    assert mirror["document"]["outline_block_ids"] == [heading_blocks[0]["id"]]
    assert table_blocks[0]["provenance"]["reconstructor"] == "metadata_table_like_region_reconstructor"
    assert table_blocks[0]["quality"]["column_count"] == 10
    assert "document.field.起始日期" in fact_predicates
    assert "document_metadata" in mirror["semantics"]["views"]
    assert mirror["document"]["document_type_candidates"][0]["type"] == "bank_statement"
    assert "bank_statement" in mirror["semantics"]["views"]
    assert any(node["kind"] == "fact" for node in mirror["graph"]["nodes"])
    assert mirror["pages"][0]["quality"]["evidence_coverage"] == 1.0
    assert mirror["quality"]["coverage"]["residual_ratio"] == 0.0
    gate_ids = {gate["id"] for gate in mirror["quality"]["gates"]}
    assert {"gate:region_ownership", "gate:token_conservation", "gate:residual_ratio", "gate:table_numeric_parse"} <= gate_ids
    assert mirror["quality"]["tables"]["numeric_parse_score"] == 1.0


def test_mirror_core_links_logical_tables_across_pages():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                width=200,
                height=200,
                tables=[
                    TableBlock(
                        table_id="pt_1_0",
                        headers=["项目", "金额"],
                        page=1,
                        bbox=[20.0, 40.0, 180.0, 160.0],
                    )
                ],
            ),
            PageContent(
                page_number=2,
                width=200,
                height=200,
                tables=[
                    TableBlock(
                        table_id="pt_2_0",
                        headers=["项目", "金额"],
                        page=2,
                        bbox=[20.0, 40.0, 180.0, 160.0],
                    )
                ],
            ),
        ],
        logical_tables=[
            LogicalTable(
                logical_id="lt_0",
                table_id="lt_0",
                source_physical_ids=["pt_1_0", "pt_2_0"],
                source_pages=[1, 2],
                merge_confidence=0.91,
            )
        ],
    )

    mirror = MirrorCoreVNext().process(result).to_dict()

    same_table_edges = [edge for edge in mirror["graph"]["edges"] if edge["type"] == "same_table"]
    continues_edges = [edge for edge in mirror["graph"]["edges"] if edge["type"] == "continues"]
    continuity_gate = next(gate for gate in mirror["quality"]["gates"] if gate["id"] == "gate:cross_page_continuity")
    assert len(same_table_edges) == 1
    assert len(continues_edges) == 1
    assert same_table_edges[0]["metadata"]["logical_id"] == "lt_0"
    assert continues_edges[0]["metadata"]["logical_id"] == "lt_0"
    assert same_table_edges[0]["confidence"] == 0.91
    assert continuity_gate["status"] == "pass"
    assert continuity_gate["details"]["expected_continuation_edges"] == 1
    assert continuity_gate["details"]["actual_continuation_edges"] == 1


def test_mirror_core_pdf_path_uses_topology_text_blocks():
    with TemporaryDirectory() as td:
        pdf_path = Path(td) / "native.pdf"
        canvas = canvas_mod.Canvas(str(pdf_path), pagesize=(200, 200))
        canvas.drawString(36, 128, "Hello Evidence")
        canvas.save()

        mirror = MirrorCoreVNext().process(pdf_path).to_dict()

    assert mirror["diagnostics"]["pipeline"][1]["stage"] == "page_topology_segmentation"
    assert mirror["diagnostics"]["pipeline"][1]["status"] == "ok"
    assert any(block["type"] == "paragraph" and "Hello Evidence" in block["text"] for block in mirror["blocks"])
    assert not any(block["role"] == "evidence_only_page" for block in mirror["blocks"])


def _reconstruction_context(plane: EvidencePlane) -> ReconstructionContext:
    atoms = [
        *plane.evidence.text_atoms,
        *plane.evidence.visual_atoms,
        *plane.evidence.image_atoms,
        *plane.evidence.vector_atoms,
    ]
    atom_by_id = {atom.id: atom for atom in atoms}
    atom_text = {atom.id: str(atom.text or "") for atom in plane.evidence.text_atoms}
    return ReconstructionContext(evidence_plane=plane, atom_by_id=atom_by_id, atom_text=atom_text)
