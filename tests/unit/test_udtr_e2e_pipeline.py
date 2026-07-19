from docmirror.models.mirror.core import MirrorCoreVNext, MirrorOptions
from docmirror.models.mirror.vnext import BlockType
from tests.unit.test_mirror_json_vnext import _sample_parse_result


def test_udtr_e2e_bank_statement():
    result = _sample_parse_result()
    mirror = MirrorCoreVNext().process(result, options=MirrorOptions(profile="canonical_full")).mirror
    assert mirror.document.title
    assert len(mirror.pages) >= 1
    tables = [b for b in mirror.blocks if b.type == BlockType.TABLE]
    assert len(tables) >= 1
    grid = tables[0].content.get("grid", {})
    assert len(grid.get("columns", [])) >= 6
    assert len(grid.get("cells", [])) >= 10
    headings = [b for b in mirror.blocks if b.type == BlockType.HEADING]
    assert len(headings) >= 1
    kv = [b for b in mirror.blocks if b.type == BlockType.KEY_VALUE_GROUP]
    assert len(kv) >= 1
    edge_types = {e.type for e in mirror.graph.edges if hasattr(e, "type")}
    assert "contains" in edge_types
    assert "reading_next" in edge_types
    assert mirror.quality.gates
    assert "bank_statement" in mirror.semantics.views
    assert mirror.diagnostics.pipeline
    assert mirror.mirror.schema_version == "1.0.7"
