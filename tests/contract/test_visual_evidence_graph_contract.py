"""W7-01: Visual Evidence Graph contract tests (schema + resolvability)."""

import pytest
from docmirror.models.visual_evidence import VisualNode, VisualEdge, VisualEvidenceGraph
from docmirror.evidence.visual_graph import build_visual_evidence_graph


class MockText:
    def __init__(self, content="", confidence=1.0, bbox=None, source_refs=None):
        self.content = content
        self.confidence = confidence
        self.bbox = bbox
        self.source_refs = source_refs or []
        self.mirror_role = ""
        self.level = ""

class MockPage:
    def __init__(self, page_number=1, width=595, height=842):
        self.page_number = page_number
        self.width = width
        self.height = height
        self.confidence = 1.0
        self.texts = []
        self.tables = []
        self.key_values = []

class MockResult:
    def __init__(self):
        self.pages = []


def test_graph_schema_roundtrip():
    """VisualEvidenceGraph must round-trip through to_dict/from_dict."""
    g = VisualEvidenceGraph(document_id="doc_001", task_id="task_001")
    g.add_page(1, width=595, height=842, image_ref="page_images/page_001.png")
    g.add_node(VisualNode(id="block:p1:b0", kind="block", label="Header",
                           page=1, bbox=[20, 40, 520, 90], confidence=0.98))
    g.add_node(VisualNode(id="field:invoice.total", kind="field", label="total",
                           page=1, bbox=[400, 700, 500, 720], confidence=0.95,
                           value_preview="100.00", field_path="invoice.total",
                           source_refs=["cell:p1:t0:r0:c0"]))
    g.add_edge(VisualEdge(id="e1", type="contains", from_node="block:p1:b0",
                           to_node="field:invoice.total", confidence=1.0))

    d = g.to_dict()
    assert d["version"] == 1
    assert d["document_id"] == "doc_001"
    assert len(d["nodes"]) == 2
    assert len(d["edges"]) == 1

    g2 = VisualEvidenceGraph.from_dict(d)
    assert g2.document_id == "doc_001"
    assert len(g2.nodes) == 2
    assert len(g2.edges) == 1
    assert g2.nodes["block:p1:b0"].kind == "block"
    assert g2.nodes["field:invoice.total"].field_path == "invoice.total"


def test_graph_from_mock_result():
    """build_visual_evidence_graph must produce page, block, table, cell nodes."""
    result = MockResult()
    page = MockPage(page_number=1, width=595, height=842)
    page.texts.append(MockText(content="Test text block",
                                confidence=0.95,
                                bbox=[20, 40, 520, 90],
                                source_refs=["text:p1:span1"]))
    result.pages.append(page)

    graph = build_visual_evidence_graph(result, document_id="doc_X", task_id="task_X")
    d = graph.to_dict()

    assert len(d["pages"]) == 1
    assert d["pages"][0]["page"] == 1
    nodes = d["nodes"]
    assert any(n["kind"] == "page" for n in nodes.values())
    assert any(n["kind"] == "block" for n in nodes.values())

    page_node = [n for n in nodes.values() if n["kind"] == "page"][0]
    block_node = [n for n in nodes.values() if n["kind"] == "block"][0]
    assert block_node["bbox"] == [20, 40, 520, 90]
    assert block_node["confidence"] == 0.95


def test_node_resolvability():
    """resolve_node and resolve_field must work on the graph."""
    g = VisualEvidenceGraph(document_id="d1")
    g.add_node(VisualNode(id="field:f1", kind="field", label="amount",
                           field_path="inv.amount", page=1))

    assert g.resolve_node("field:f1") is not None
    assert g.resolve_node("nonexistent") is None
    assert g.resolve_field("inv.amount") is not None
    assert g.resolve_field("nonexistent") is None


def test_nodes_by_kind_and_page():
    """nodes_by_page and nodes_by_kind must filter correctly."""
    g = VisualEvidenceGraph()
    g.add_node(VisualNode(id="b1", kind="block", page=1))
    g.add_node(VisualNode(id="b2", kind="block", page=2))
    g.add_node(VisualNode(id="f1", kind="field", page=1))

    assert len(g.nodes_by_page(1)) == 2
    assert len(g.nodes_by_page(2)) == 1
    assert len(g.nodes_by_kind("block")) == 2
    assert len(g.nodes_by_kind("field")) == 1


def test_nodes_needing_review():
    """nodes_needing_review must return only nodes with review != auto_accepted."""
    g = VisualEvidenceGraph()
    g.add_node(VisualNode(id="ok", kind="block", review="auto_accepted"))
    g.add_node(VisualNode(id="nr", kind="field", review="needs_review"))
    g.add_node(VisualNode(id="ne", kind="field", review="needs_evidence"))

    need = g.nodes_needing_review()
    assert len(need) == 2
    assert {n.id for n in need} == {"nr", "ne"}
