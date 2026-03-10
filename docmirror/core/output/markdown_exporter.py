"""
Markdown Exporter (OmniDocBench Adapt)
======================================

将 CoreExtractor 产出的 BaseResult Convert为 OmniDocBench 评测所需的
per-page Markdown File。

OmniDocBench 评估流程::

    model Parse PDF → 每页 .md → 评测Script对比 GT → 分数

核心Map:
    - title  → # / ## / ### (按 heading_level)
    - text   → Paragraph (双Newline分隔)
    - table  → Markdown table (header + |---| + rows)
    - formula → $$LaTeX$$
    - key_value / footer / image → Skip (benchmark 不评测)
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import List, Optional

from docmirror.models.domain import BaseResult, Block, PageLayout

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 公共 API
# ═══════════════════════════════════════════════════════════════════════════════


def export_document(result: BaseResult) -> List[str]:
    """将整个 BaseResult Convert为按页分割的 Markdown List。

    Args:
        result: CoreExtractor 产出的ImmutableExtractResult。

    Returns:
        List[str]: each元素是一页的 Markdown 文本。
        Index 0 对应第一页。
    """
    return [export_page(page) for page in result.pages]


def export_page(page: PageLayout) -> str:
    """将单页 PageLayout Convert为 Markdown 字符串。

    Blocks 按 reading_order Sort后依次渲染。
    相邻块之间用双Newline分隔 (Markdown ParagraphSeparator)。

    Args:
        page: 单页版面结构。

    Returns:
        完整的 Markdown 字符串。
    """
    if not page.blocks:
        return ""

    sorted_blocks = sorted(page.blocks, key=lambda b: b.reading_order)
    parts: List[str] = []

    for block in sorted_blocks:
        rendered = _render_block(block)
        if rendered is not None:
            parts.append(rendered)

    return "\n\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# 逐Type渲染
# ═══════════════════════════════════════════════════════════════════════════════


def _render_block(block: Block) -> Optional[str]:
    """based on block_type Dispatch渲染。

    Returns:
        渲染后的 Markdown 片段, 或 None 表示Skip。
    """
    renderer = _RENDERERS.get(block.block_type)
    if renderer is None:
        return None
    return renderer(block)


def _render_title(block: Block) -> Optional[str]:
    """Title → # 层级。"""
    text = _get_text(block)
    if not text:
        return None

    level = block.heading_level or 1
    prefix = "#" * min(level, 6)
    return f"{prefix} {text}"


def _render_text(block: Block) -> Optional[str]:
    """Body textParagraph → 纯文本。"""
    text = _get_text(block)
    return text if text else None


def _render_table(block: Block) -> Optional[str]:
    """Table → Markdown table。

    raw_content Format: List[List[str]]
    第一行视为 header，后续行为 data。
    如果only一行，也Output为 header-only table。
    """
    rows = block.raw_content
    if not rows or not isinstance(rows, list):
        return None

    # 清洗: ensureeach cell 都是字符串
    clean_rows: List[List[str]] = []
    for row in rows:
        if not isinstance(row, (list, tuple)):
            continue
        clean_rows.append([_clean_cell(c) for c in row])

    if not clean_rows:
        return None

    # 统一列数 (取最大列数)
    max_cols = max(len(r) for r in clean_rows)
    for row in clean_rows:
        while len(row) < max_cols:
            row.append("")

    # 渲染
    header = clean_rows[0]
    lines: List[str] = []

    # Header row
    lines.append("| " + " | ".join(header) + " |")
    # Separator row
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    # Data rows
    for row in clean_rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def _render_formula(block: Block) -> Optional[str]:
    """Display formula → $$LaTeX$$。"""
    latex = _get_text(block)
    if not latex:
        return None

    # 去掉may已存在的 $ 定界符
    latex = latex.strip()
    if latex.startswith("$$") and latex.endswith("$$"):
        return latex
    if latex.startswith("$") and latex.endswith("$") and not latex.startswith("$$"):
        latex = latex[1:-1]

    return f"$$\n{latex}\n$$"


# ═══════════════════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════════════════


def _get_text(block: Block) -> str:
    """从 Block 中Extract文本。

    优先从 raw_content Extract (如果是 str)，
    otherwise从 spans 拼接。
    """
    if isinstance(block.raw_content, str):
        return _normalize_text(block.raw_content)

    # 从 spans 拼接
    if block.spans:
        return _normalize_text(" ".join(s.text for s in block.spans))

    return ""


def _normalize_text(text: str) -> str:
    """Text normalization: NFC + 去除多余Whitespace。"""
    text = unicodedata.normalize("NFC", text)
    # 多个空格/制 table符Merge为单个空格
    text = re.sub(r"[ \t]+", " ", text)
    # 去除首尾Whitespace
    text = text.strip()
    return text


def _clean_cell(value) -> str:
    """清洗Table cell 值。"""
    if value is None:
        return ""
    s = str(value).strip()
    # Pipe符会破坏 Markdown table 语法
    s = s.replace("|", "\\|")
    # 换Line merging
    s = s.replace("\n", " ")
    return s


# ═══════════════════════════════════════════════════════════════════════════════
# 渲染器Registry
# ═══════════════════════════════════════════════════════════════════════════════

_RENDERERS = {
    "title": _render_title,
    "text": _render_text,
    "table": _render_table,
    "formula": _render_formula,
    # belowTypeSkip
    "key_value": None,
    "footer": None,
    "image": None,
}
