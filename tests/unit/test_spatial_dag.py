import pytest
from docmirror.core.spatial.dag import SpatialNode, LayoutGraph

def test_layout_graph_find_nearest_right():
    # 模拟同行不同列的数据
    # 【借款金额】 [    300,000    ]
    nodes = [
        SpatialNode(id="n1", text="借款金额", x0=10, y0=100, x1=50, y1=110),
        SpatialNode(id="n2", text="300,000", x0=60, y0=100, x1=90, y1=110),
        # 干扰项：同行但距离极远
        SpatialNode(id="n3", text="人民币", x0=150, y0=100, x1=180, y1=110),
        # 干扰项：距离近但在上一行
        SpatialNode(id="n4", text="干扰", x0=60, y0=80, x1=90, y1=90),
    ]
    
    graph = LayoutGraph(nodes)
    res = graph.find_nearest_right("借款金额")
    
    assert res is not None
    assert res.text == "300,000"

def test_layout_graph_find_nearest_below():
    # 模拟上下折行的数据，容忍 X 轴轻微偏移
    # 【机构名称】
    # 【中国建设银行】
    nodes = [
        SpatialNode(id="n1", text="机构名称", x0=10, y0=100, x1=50, y1=110),
        SpatialNode(id="n2", text="中国建设银行", x0=12, y0=115, x1=60, y1=125),  # 下方最近
        SpatialNode(id="n3", text="另外一行", x0=10, y0=150, x1=50, y1=160),  # 下方较远
        SpatialNode(id="n4", text="旁边的文字", x0=80, y0=100, x1=120, y1=110), # 右侧
    ]
    
    graph = LayoutGraph(nodes)
    res = graph.find_nearest_below("机构名称")
    
    assert res is not None
    assert res.text == "中国建设银行"

def test_layout_graph_resolve_anchor_value():
    nodes_right = [
        SpatialNode(id="n1", text="余额", x0=10, y0=100, x1=30, y1=110),
        SpatialNode(id="n2", text="50,000", x0=35, y0=100, x1=60, y1=110), # 右侧优先
        SpatialNode(id="n3", text="干扰下", x0=10, y0=120, x1=30, y1=130),
    ]
    assert LayoutGraph(nodes_right).resolve_anchor_value("余额") == "50,000"
    
    nodes_below = [
        SpatialNode(id="n1", text="余额", x0=10, y0=100, x1=30, y1=110),
        SpatialNode(id="n2", text="50,000", x0=12, y0=120, x1=40, y1=130), # 下方 fallback
    ]
    assert LayoutGraph(nodes_below).resolve_anchor_value("余额") == "50,000"
    
    nodes_missing = [
        SpatialNode(id="n1", text="余额", x0=10, y0=100, x1=30, y1=110),
    ]
    assert LayoutGraph(nodes_missing).resolve_anchor_value("余额") is None
