# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""MCP (Model Context Protocol) server CLI command.

Registered as ``docmirror mcp [--transport stdio|sse] [--port PORT] [--host HOST]``.
Delegates to :mod:`docmirror.server.mcp` for the actual server implementation.
"""

from __future__ import annotations

import click


@click.command("mcp")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    show_default=True,
    help="Transport protocol. Use stdio for MCP clients (Claude Desktop, Cursor). "
    "Use sse for remote HTTP access.",
)
@click.option(
    "--port",
    type=int,
    default=8001,
    show_default=True,
    help="Port for SSE transport (ignored for stdio).",
)
@click.option(
    "--host",
    type=str,
    default="0.0.0.0",
    show_default=True,
    help="Host for SSE transport (ignored for stdio).",
)
def mcp(transport: str, port: int, host: str) -> None:
    """Start the DocMirror MCP (Model Context Protocol) server.

    Exposes document parsing as MCP tools (parse_document, parse_document_from_bytes)
    for use by LLM clients such as Claude Desktop, Cursor, and Codex.
    """
    from docmirror.server.mcp import run_sse, run_stdio

    if transport == "stdio":
        run_stdio()
    else:
        run_sse(host=host, port=port)
