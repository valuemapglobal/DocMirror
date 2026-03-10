"""
VLM OutputPost-processing + Ensemble 融合 (VLM Postprocess + Ensemble)
============================================================

Parse VLM (Qwen2.5-VL) 的 Markdown Output，并与 Pipeline ExtractResult融合。

核心逻辑:
    1. parse_vlm_markdown:  将 VLM Markdown Parse为 Block List
    2. ensemble_results:    VLM + Pipeline Result择优融合
    3. vlm_markdown_to_benchmark_md: VLM Markdown → OmniDocBench 评测Format

融合策略 (Hybrid):
    - Digital PDF: Pipeline 文本 (100% 准确) + VLM Table/Formula
    - Scanned document:   VLM 优先 (Pipeline OCR 质量低)
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# VLM Markdown Clean
# ═══════════════════════════════════════════════════════════════════════════════

def clean_vlm_markdown(md: str) -> str:
    """Clean VLM Output的 Markdown，去除常见瑕疵。

    VLM 常见问题:
      - Output ```markdown ... ``` 包裹
      - 多余的解释文字
      - 思考过程 <think>...</think>
      - Empty row过多
    """
    if not md:
        return ""

    # 去除 <think>...</think> 块 (Qwen3.5 的思考过程)
    md = re.sub(r"<think>.*?</think>", "", md, flags=re.DOTALL)

    # 去除 ```markdown ... ``` 包裹
    md = re.sub(r"^```(?:markdown|md|html)?\s*\n", "", md)
    md = re.sub(r"\n```\s*$", "", md)

    # 去除开头的解释性文字 (如 "Here is the converted markdown:")
    lines = md.split("\n")
    while lines and _is_meta_line(lines[0]):
        lines.pop(0)

    # 压缩连续Empty row (3+ → 2)
    md = "\n".join(lines)
    md = re.sub(r"\n{3,}", "\n\n", md)

    return md.strip()


def _is_meta_line(line: str) -> bool:
    """判断Whether为 VLM add的元Information行。"""
    line = line.strip().lower()
    if not line:
        return False
    meta_patterns = [
        "here is", "here's", "below is", "the converted",
        "i've converted", "i have converted",
        "markdown output", "markdown format",
    ]
    return any(p in line for p in meta_patterns)


# ═══════════════════════════════════════════════════════════════════════════════
# VLM Markdown → OmniDocBench 评测Format
# ═══════════════════════════════════════════════════════════════════════════════

def vlm_markdown_to_benchmark_md(vlm_md: str) -> str:
    """将 VLM Markdown 直接Convert为 OmniDocBench 评测Format。

    OmniDocBench 评测Script期望:
      - 文本: 纯 Markdown Paragraph
      - Table: HTML <table> Format (用于 TEDS 评分)
      - Formula: $...$ 或 $$...$$ LaTeX (用于 CDM 评分)
      - Title: # ## ### (用于结构评分)

    VLM 的Outputtypicallyalready符合这个Format, 只需Clean。
    """
    md = clean_vlm_markdown(vlm_md)

    # ensure Markdown Table转为 HTML (某些 VLM mayOutput Markdown Table)
    md = _convert_md_tables_to_html(md)

    return md


# ═══════════════════════════════════════════════════════════════════════════════
# Markdown Table → HTML TableConvert
# ═══════════════════════════════════════════════════════════════════════════════

# Markdown Table分隔行: | --- | --- | 或 |:---:|:---|---:|
_MD_TABLE_SEP_RE = re.compile(r"^\|[\s:]*-+[\s:]*(\|[\s:]*-+[\s:]*)*\|?\s*$")


def _convert_md_tables_to_html(md: str) -> str:
    """将 Markdown Table转为 HTML <table>。

    VLM mayOutput Markdown Format的Table而非 HTML，need toConvert以获得 TEDS 评分。
    """
    lines = md.split("\n")
    result_lines = []
    i = 0

    while i < len(lines):
        # Detect Markdown Tablebegin
        if i + 1 < len(lines) and _MD_TABLE_SEP_RE.match(lines[i + 1].strip()):
            # 收集整个Table
            table_lines = [lines[i]]  # Table header行
            i += 2  # Skip分隔行
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1

            # Convert
            html = _md_table_lines_to_html(table_lines)
            result_lines.append(html)
        else:
            result_lines.append(lines[i])
            i += 1

    return "\n".join(result_lines)


def _md_table_lines_to_html(table_lines: List[str]) -> str:
    """将 Markdown Table行List转为 HTML。"""
    if not table_lines:
        return ""

    def parse_row(line: str) -> List[str]:
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|"):
            line = line[:-1]
        return [cell.strip() for cell in line.split("|")]

    html_parts = ["<table>"]

    # Table header
    header_cells = parse_row(table_lines[0])
    html_parts.append("<thead><tr>")
    for cell in header_cells:
        html_parts.append(f"<th>{cell}</th>")
    html_parts.append("</tr></thead>")

    # Data行
    if len(table_lines) > 1:
        html_parts.append("<tbody>")
        for line in table_lines[1:]:
            cells = parse_row(line)
            html_parts.append("<tr>")
            for cell in cells:
                html_parts.append(f"<td>{cell}</td>")
            html_parts.append("</tr>")
        html_parts.append("</tbody>")

    html_parts.append("</table>")
    return "".join(html_parts)


# ═══════════════════════════════════════════════════════════════════════════════
# Ensemble 融合
# ═══════════════════════════════════════════════════════════════════════════════

def ensemble_page_markdown(
    vlm_md: Optional[str],
    pipeline_md: Optional[str],
    has_text_layer: bool = True,
) -> str:
    """融合 VLM 和 Pipeline 的 Markdown Output。

    融合策略:
      1. VLM 可用 + Scanned document → VLM 优先 (Pipeline OCR 质量低)
      2. VLM 可用 + Digital PDF → VLM 优先但用 Pipeline Validate
      3. VLM 不可用 → Pipeline 兜底

    Args:
        vlm_md: VLM Output的 Markdown (may为 None)
        pipeline_md: Pipeline Output的 Markdown (may为 None)
        has_text_layer: PDF Whether有文字 layer

    Returns:
        最终 Markdown 字符串
    """
    vlm_clean = clean_vlm_markdown(vlm_md) if vlm_md else ""
    pipeline_clean = pipeline_md.strip() if pipeline_md else ""

    # 情况 1: VLM 无Output → Pipeline 兜底
    if not vlm_clean:
        logger.debug("[VLM-Ensemble] VLM 无Output, using Pipeline")
        return pipeline_clean

    # 情况 2: Pipeline 无Output → VLM
    if not pipeline_clean:
        logger.debug("[VLM-Ensemble] Pipeline 无Output, using VLM")
        return vlm_markdown_to_benchmark_md(vlm_clean)

    # 情况 3: 两者都有 → 择优融合
    vlm_score = _score_markdown_quality(vlm_clean)
    pipeline_score = _score_markdown_quality(pipeline_clean)

    logger.info(
        f"[VLM-Ensemble] VLM={vlm_score:.1f}, Pipeline={pipeline_score:.1f}, "
        f"text_layer={has_text_layer}"
    )

    # Scanned document: VLM 几乎总是更好
    if not has_text_layer:
        return vlm_markdown_to_benchmark_md(vlm_clean)

    # Digital PDF: VLM typicallyTable/Formula更好
    # 如果 VLM 得分显著高于 Pipeline, 用 VLM
    if vlm_score > pipeline_score * 0.9:
        return vlm_markdown_to_benchmark_md(vlm_clean)

    # otherwise用 Pipeline (Digital PDF 文本 layer更可靠)
    return pipeline_clean


def _score_markdown_quality(md: str) -> float:
    """简单打分: 评估 Markdown 内容的质量。

    评分维度:
      - 长度 (越长越maycontains更多Information)
      - 结构标记 (Table HTML, LaTeX Formula, Title)
      - 无效内容Ratio (乱码, 重复)
    """
    if not md:
        return 0.0

    score = 0.0

    # 长度分 (上限 100)
    score += min(len(md) / 50.0, 100.0)

    # 结构分
    if "<table" in md.lower():
        score += 30  # 有 HTML Table
    if re.search(r"\|.*\|.*\|", md):
        score += 15  # 有 Markdown Table
    if re.search(r"\$.*?\$", md):
        score += 20  # 有 LaTeX Formula
    if re.search(r"^#{1,3}\s", md, re.MULTILINE):
        score += 10  # 有Title

    # 惩罚: 连续Duplicate rows
    lines = md.split("\n")
    unique_lines = set(l.strip() for l in lines if l.strip())
    if len(lines) > 5:
        uniqueness = len(unique_lines) / len(lines)
        if uniqueness < 0.5:
            score *= 0.5  # 大量重复, 减半

    return score
