"""
核心ImmutableData模型 (Frozen Domain Models)
==========================================

本Moduledefine了 MultiModal 的"Data地基"。All models use ``frozen=True``,
一旦由 ``CoreExtractor`` 生成便不可修改 — 这是整个系统"可追溯"的基石。

设计决策:
    - frozen dataclass 而非 Pydantic: Extract layer追求极致性能，avoidValidate开销。
    - str block_id: UUID 字符串，保证Cross-page merge后仍Global唯一。
    - reading_order: 显式整数，由 CoreExtractor 在GlobalAnalyze阶段赋值。
    - raw_content: Union Type，按 block_type 存储原始内容:
        - "text"/"title": str
        - "table":        List[List[str]] (二维数组)
        - "image":        bytes
        - "formula":      str (LaTeX)
    - heading_level: Title layer级 (1=h1, 2=h2, 3=h3)，仅 title Block 有值。
    - caption: Association的图注文字，仅 image Block 有值。
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any, Dict, List, Literal, Optional, Tuple, Union


@dataclasses.dataclass(frozen=True)
class Style:
    """文本视觉样式 — 由 PyMuPDF 的 span PropertyExtract。"""
    font_name: str = ""
    font_size: float = 0.0
    color: str = "#000000"
    is_bold: bool = False
    is_italic: bool = False


@dataclasses.dataclass(frozen=True)
class TextSpan:
    """
    文本片段 — 同一 Block 内具有相同样式的连续文字。

    bbox using PDF StandardCoordinates (x0, y0, x1, y1)，
    y 轴向下增长，单位为 pt (1/72 inch)。
    """
    text: str
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1)
    style: Style = dataclasses.field(default_factory=Style)


@dataclasses.dataclass(frozen=True)
class Block:
    """
    Page内容块 — PDF Document的最小结构单元。

    each Block 代 table一个语义完整的内容区域:
    Table、Title、Body textParagraph、图像或Formula。
    """
    block_id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4())[:8])
    block_type: Literal["text", "table", "image", "title", "key_value", "footer", "formula"] = "text"
    spans: Tuple[TextSpan, ...] = ()  # frozen need to tuple
    bbox: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    reading_order: int = 0
    page: int = 0
    # 原始内容 — 按Type存储
    raw_content: Union[str, List[List[str]], Dict[str, str], bytes, None] = None
    # Title layer级 (1=h1, 2=h2, 3=h3)，仅 title Block 有值
    heading_level: Optional[int] = None
    # 图注文字，仅 image Block 有值
    caption: Optional[str] = None


@dataclasses.dataclass(frozen=True)
class PageLayout:
    """
    单页版面结构 — containsall Block 和语义区域划分。

    semantic_zones 示例:
        {"header": ["blk_a1"], "body": ["blk_b2", "blk_b3"], "footer": ["blk_c4"]}
    """
    page_number: int = 0
    width: float = 0.0
    height: float = 0.0
    blocks: Tuple[Block, ...] = ()  # frozen need to tuple
    semantic_zones: Dict[str, List[str]] = dataclasses.field(default_factory=dict)
    is_scanned: bool = False


@dataclasses.dataclass(frozen=True)
class BaseResult:
    """
    核心ExtractResult — Immutable。

    这是 CoreExtractor 的唯一Output，代 table对 PDF 最原始、最客观的结构化描述。
    一旦生成便不可修改，all后续Processing均作为"增强"存在于 EnhancedResult 中。
    """
    document_id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    pages: Tuple[PageLayout, ...] = ()  # frozen need to tuple
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)
    full_text: str = ""

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def all_blocks(self) -> List[Block]:
        """按 reading_order ReturnsallPage的 Block。"""
        blocks = []
        for page in self.pages:
            blocks.extend(page.blocks)
        return sorted(blocks, key=lambda b: (b.page, b.reading_order))

    @property
    def table_blocks(self) -> List[Block]:
        """仅Returns table Type的 Block。"""
        return [b for b in self.all_blocks if b.block_type == "table"]

    @property
    def entities(self) -> Dict[str, str]:
        """Mergeall key_value Block 的Data。"""
        result: Dict[str, str] = {}
        for b in self.all_blocks:
            if b.block_type == "key_value" and isinstance(b.raw_content, dict):
                result.update(b.raw_content)
        return result
