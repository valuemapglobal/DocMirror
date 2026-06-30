"""Markdown and chunk projections from MirrorJson vNext."""

from __future__ import annotations

from typing import Any


def _blocks_by_id(mirror: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(block.get("id")): block for block in mirror.get("blocks", []) if block.get("id")}


def _reading_blocks(mirror: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = _blocks_by_id(mirror)
    flow_id = mirror.get("document", {}).get("primary_reading_flow_id")
    flows = mirror.get("graph", {}).get("reading_flows", [])
    for flow in flows:
        if not flow_id or flow.get("flow_id") == flow_id:
            return [blocks[node_id] for node_id in flow.get("node_ids", []) if node_id in blocks]
    return [
        block for block in mirror.get("blocks", []) if not block.get("quality", {}).get("suppressed_from_reading_flow")
    ]


def _table_markdown(block: dict[str, Any]) -> str:
    grid = block.get("content", {}).get("grid", {})
    columns = grid.get("columns") or []
    headers = [str(col.get("header", "")) for col in columns]
    cells = grid.get("cells") or []
    rows: dict[int, dict[int, str]] = {}
    for cell in cells:
        rows.setdefault(int(cell.get("row_index", 0)), {})[int(cell.get("col_index", 0))] = str(cell.get("text", ""))
    if not headers and rows:
        max_col = max(max(row) for row in rows.values())
        headers = [rows.get(0, {}).get(i, "") for i in range(max_col + 1)]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row_index in sorted(idx for idx in rows if idx != 0):
        row = rows[row_index]
        lines.append("| " + " | ".join(row.get(i, "") for i in range(len(headers))) + " |")
    return "\n".join(lines)


def _block_text(block: dict[str, Any]) -> str:
    if block.get("type") == "table":
        return _table_markdown(block)
    return str(block.get("text", ""))


def export_markdown_from_vnext(mirror: dict[str, Any]) -> str:
    parts: list[str] = []
    for block in _reading_blocks(mirror):
        text = _block_text(block)
        if not text:
            continue
        if block.get("type") == "heading" or block.get("role") == "h1":
            parts.append(f"# {text}")
        else:
            parts.append(text)
    return "\n\n".join(parts)


def export_chunks_from_vnext(mirror: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for block in _reading_blocks(mirror):
        text = _block_text(block)
        if not text:
            continue
        block_id = str(block.get("id", f"block:{len(chunks)}"))
        block_type = str(block.get("type", "text"))
        chunks.append(
            {
                "chunk_id": f"{block_id}:chunk:0000",
                "chunk_type": "section" if block_type == "heading" else block_type,
                "text": text,
                "block_id": block_id,
                "evidence_ids": block.get("evidence_ids", []),
            }
        )
    return chunks
