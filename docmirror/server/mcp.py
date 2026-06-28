# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""MCP (Model Context Protocol) server — expose DocMirror as LLM-callable tools.

The MCP protocol is emerging as the standard for LLM-tool communication
(Claude, Cursor, Codex, etc.). This server exposes DocMirror's document
parsing capabilities as MCP tools that any MCP-compatible LLM client can use.

Usage:
    # Run directly (stdio transport — for Claude Desktop, Cursor, etc.)
    python -m docmirror.server.mcp

    # With options (HTTP + SSE transport)
    python -m docmirror.server.mcp --transport sse --port 8080

Exposed tools:
    - parse_document(path, mode?) → DMIR JSON
    - parse_document_from_bytes(data, filename, mode?) → DMIR JSON
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Lazily import DocMirror engine — avoids import cost at module load time
_core = None


def _get_core():
    """Lazy-load DocMirror core."""
    global _core
    if _core is None:
        try:
            from docmirror.input.entry.factory import perceive_document, PerceiveOptions
            from docmirror.output.dmir import serialize_dmir

            _core = {
                "perceive_document": perceive_document,
                "PerceiveOptions": PerceiveOptions,
                "serialize_dmir": serialize_dmir,
            }
        except ImportError as e:
            raise ImportError(
                "DocMirror core is not installed. Install with: pip install docmirror"
            ) from e
    return _core


_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "parse_document",
        "description": "Parse a document file (PDF, image, Office) and return structured DMIR JSON. "
        "DMIR (DocMirror Intermediate Representation) is a lossless, framework-agnostic format "
        "that captures tables, texts, key-values, quality scores, and evidence provenance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the document file.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "fast", "balanced", "accurate"],
                    "description": "Parse mode. 'auto' picks based on file type.",
                    "default": "auto",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "parse_document_from_bytes",
        "description": "Parse a document from raw bytes (e.g. from an API response) "
        "and return structured DMIR JSON. The filename is used to infer the file type.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "string",
                    "description": "Base64-encoded document bytes.",
                },
                "filename": {
                    "type": "string",
                    "description": "Original filename with extension (e.g. 'statement.pdf').",
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "fast", "balanced", "accurate"],
                    "description": "Parse mode. 'auto' picks based on file type.",
                    "default": "auto",
                },
            },
            "required": ["data", "filename"],
        },
    },
]


def _parse_document_impl(file_path: str, mode: str = "auto") -> str:
    """Parse a document at *file_path* and return DMIR JSON string.

    Args:
        file_path: Path to the document file.
        mode: Parse mode.

    Returns:
        DMIR JSON string.
    """
    core = _get_core()
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {file_path}")

    options = core["PerceiveOptions"](parse_mode=mode) if mode != "auto" else core["PerceiveOptions"]()
    result = core["perceive_document"](path, options)
    dmir = core["serialize_dmir"](result)
    return json.dumps(dmir, indent=2, ensure_ascii=False, default=str)


def _parse_bytes_impl(data_b64: str, filename: str, mode: str = "auto") -> str:
    """Parse a document from base64-encoded bytes and return DMIR JSON string.

    Args:
        data_b64: Base64-encoded document bytes.
        filename: Original filename (used to infer type).
        mode: Parse mode.

    Returns:
        DMIR JSON string.
    """
    import base64
    import tempfile

    core = _get_core()

    raw_bytes = base64.b64decode(data_b64)
    suffix = Path(filename).suffix or ".bin"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(raw_bytes)
        tmp_path = tmp.name

    try:
        options = core["PerceiveOptions"](parse_mode=mode) if mode != "auto" else core["PerceiveOptions"]()
        result = core["perceive_document"](Path(tmp_path), options)
        dmir = core["serialize_dmir"](result)
        return json.dumps(dmir, indent=2, ensure_ascii=False, default=str)
    finally:
        os.unlink(tmp_path)


def _build_fastmcp() -> Any:
    """Build and return a FastMCP server.

    This factory function allows the server to be imported and run from
    multiple entry points (CLI, ASGI, direct Python import).
    """
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        "DocMirror",
        instructions="Document parsing server using DocMirror engine. "
        "Supports PDF, images, and Office documents. Returns DMIR JSON.",
    )

    @mcp.tool(
        name="parse_document",
        description=_TOOL_DEFINITIONS[0]["description"],
    )
    def parse_document(
        file_path: str,
        mode: str = "auto",
    ) -> str:
        """Parse a document file and return DMIR JSON."""
        return _parse_document_impl(file_path, mode)

    @mcp.tool(
        name="parse_document_from_bytes",
        description=_TOOL_DEFINITIONS[1]["description"],
    )
    def parse_document_from_bytes(
        data: str,
        filename: str,
        mode: str = "auto",
    ) -> str:
        """Parse a document from base64-encoded bytes."""
        return _parse_bytes_impl(data, filename, mode)

    return mcp


def run_stdio():
    """Run MCP server over stdio transport.

    Use this for Claude Desktop, Cursor, and other MCP clients
    that connect via stdio.
    """
    mcp = _build_fastmcp()
    logger.info("Starting DocMirror MCP server (stdio transport)")
    mcp.run(transport="stdio")


def run_sse(host: str = "0.0.0.0", port: int = 8001):
    """Run MCP server over SSE (HTTP) transport.

    Use this for remote MCP clients that connect via HTTP.

    Args:
        host: Bind address.
        port: Bind port.
    """
    mcp = _build_fastmcp()
    logger.info(f"Starting DocMirror MCP server (SSE transport) on {host}:{port}")
    mcp.run(transport="sse", host=host, port=port)


def create_mcp_app() -> Any:
    """Create a FastMCP app for embedding in ASGI applications.

    Returns:
        A FastMCP instance that can be mounted in an ASGI app.
    """
    return _build_fastmcp()


__all__ = [
    "create_mcp_app",
    "run_sse",
    "run_stdio",
    "_TOOL_DEFINITIONS",
    "_parse_document_impl",
    "_parse_bytes_impl",
]


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="DocMirror MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio). SSE allows HTTP clients.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port for SSE transport (default: 8001).",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host for SSE transport (default: 0.0.0.0).",
    )

    args = parser.parse_args()

    if args.transport == "stdio":
        run_stdio()
    else:
        run_sse(host=args.host, port=args.port)
