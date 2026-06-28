#!/usr/bin/env node
/**
 * @docmirror/mcp-server — CLI entry point
 *
 * Run with:
 *   docmirror-mcp                    # Subprocess mode (spawns Python MCP server)
 *   docmirror-mcp --api-url http://localhost:8000  # REST API mode
 *   docmirror-mcp --help             # Show help
 */

import { runMcpServer } from "./index.js";

async function main() {
  const args = process.argv.slice(2);

  // Help
  if (args.includes("--help") || args.includes("-h")) {
    console.log(`
DocMirror MCP Server — v0.1.0

Exposes DocMirror's document parsing capabilities as MCP tools
for LLM clients (Claude Desktop, Cursor, Codex, etc.).

USAGE:
  docmirror-mcp                          Subprocess mode (default — spawns Python MCP server)
  docmirror-mcp --api-url <URL>          API mode — calls the DocMirror REST API
  docmirror-mcp --help                   Show this help

SUBprocess MODE:
  Requires Python 3.10+ with docmirror installed.
  The Python MCP server is spawned as a child process and stdio is forwarded.

API MODE:
  Calls the DocMirror REST API for each tool invocation.
  Use --api-url to point to a running DocMirror instance.

EXPOSED TOOLS:
  parse_document(file_path, mode?)
  parse_document_from_bytes(data, filename, mode?)

ENVIRONMENT VARIABLES:
  DOCMIRROR_API_URL   API base URL (default: http://localhost:8000)
  DOCMIRROR_PYTHON    Python executable for subprocess mode (default: python3)
`);
    process.exit(0);
  }

  // Detect mode
  const apiUrlIndex = args.indexOf("--api-url");
  const apiUrl = apiUrlIndex !== -1 ? args[apiUrlIndex + 1] : process.env.DOCMIRROR_API_URL;
  const python = process.env.DOCMIRROR_PYTHON;

  if (apiUrl) {
    await runMcpServer({ mode: "api", apiUrl });
  } else {
    await runMcpServer({ mode: "subprocess", python });
  }
}

main().catch((err) => {
  console.error("[docmirror-mcp] Fatal error:", err);
  process.exit(1);
});
