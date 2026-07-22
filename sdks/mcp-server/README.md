# @docmirror/mcp-server

> **Preview status:** this package is source-only and is not published to npm.
> Build and run it from this repository; `npx @docmirror/mcp-server` is not available yet.

MCP (Model Context Protocol) server for [DocMirror](https://valuemapglobal.github.io/DocMirror/) — universal document parsing exposed as LLM-callable tools.

Use this with Claude Desktop, Cursor, Codex, or any MCP-compatible LLM client
to parse PDFs, images, and Office documents directly from the LLM interface.

## Features

- **Two operation modes**: Subprocess (default) spawns the Python DocMirror engine; API mode calls the REST API
- **Full DMIR output**: Returns structured JSON with document sections, tables, quality metrics, and evidence
- **Zero configuration**: Works out of the box when DocMirror Python package is installed
- **Cross-platform**: The same source build works on macOS, Linux, and Windows

## Preview Build

```bash
git clone https://github.com/valuemapglobal/DocMirror.git
cd DocMirror/sdks/mcp-server
npm ci
npm run build
```

## Quick Start

### Mode 1: Subprocess (Default — requires Python DocMirror)

```bash
# The MCP server spawns the Python DocMirror MCP server as a child process
node dist/cli.js
```

Requirements:
- Python 3.10+ with this checkout installed (`pip install -e ".[mcp]"` from the repository root)
- The `docmirror` Python module must be importable

### Mode 2: API (No Python needed)

```bash
# Calls a local or self-hosted DocMirror REST API for each tool invocation
node dist/cli.js --api-url http://localhost:8000
```

## Configuration

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "docmirror": {
      "command": "node",
      "args": ["/absolute/path/to/DocMirror/sdks/mcp-server/dist/cli.js"]
    }
  }
}
```

Or with API mode:

```json
{
  "mcpServers": {
    "docmirror": {
      "command": "node",
      "args": [
        "/absolute/path/to/DocMirror/sdks/mcp-server/dist/cli.js",
        "--api-url",
        "http://localhost:8000"
      ]
    }
  }
}
```

### Cursor / Codex / Other MCP Clients

Configure the MCP server in your editor's MCP settings. The command is:

```
node /absolute/path/to/DocMirror/sdks/mcp-server/dist/cli.js
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCMIRROR_API_URL` | `http://localhost:8000` | API base URL (API mode) |
| `DOCMIRROR_PYTHON` | `python3` | Python executable (subprocess mode) |

## Exposed Tools

### `parse_document`

Parse a document file and return TaskResult JSON.

**Inputs:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | `string` | Yes | Absolute or relative path to the document file |
| `mode` | `string` | No | Parse mode: `"auto"`, `"fast"`, `"balanced"`, `"accurate"` |

**Output:** TaskResult JSON with status, per-file results, quality summary, and stable artifact roles.

### `parse_document_from_bytes`

Parse a document from raw bytes (e.g. downloaded from an API or pasted from clipboard).

**Inputs:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `data` | `string` | Yes | Base64-encoded document bytes |
| `filename` | `string` | Yes | Original filename with extension (e.g. `"statement.pdf"`) |
| `mode` | `string` | No | Parse mode: `"auto"`, `"fast"`, `"balanced"`, `"accurate"` |

## Architecture

This source preview provides **two transport strategies** for the same MCP interface:

```
┌──────────────────────────────────────────────────────────┐
│                   LLM Client (Claude Desktop, etc.)       │
└───────────────┬──────────────────────────────────────────┘
                │  MCP (JSON-RPC over stdio)
┌───────────────▼──────────────────────────────────────────┐
│          @docmirror/mcp-server (source preview)            │
│                                                           │
│  ┌──────────────────────┐   ┌──────────────────────────┐ │
│  │ Subprocess Mode       │   │ API Mode                  │ │
│  │ (default)             │   │ (--api-url)               │ │
│  │                       │   │                           │ │
│  │ spawns Python MCP     │   │ calls REST API endpoints  │ │
│  │ server, forwards      │   │ for each tool invocation  │ │
│  │ stdio passthrough     │   │ using native fetch         │ │
│  └──────────┬───────────┘   └──────────────────────────┘ │
└─────────────┬────────────────────────────────────────────┘
              │
              ▼
      DocMirror Engine (Python)
```

### Why Subprocess Mode?

The DocMirror parsing engine is built in Python (with C-extensions for OCR, layout analysis, table extraction). Rather than rewriting the entire engine in TypeScript, the MCP server wraps the Python process and proxies MCP communication over stdio. This gives you:

- **Full parsing fidelity** — Same engine as the REST API
- **Offline capable** — No network needed after initial install
- **Local privacy** — Documents never leave your machine

### When to Use API Mode

- Python is not available in your environment
- You want to connect to a remote DocMirror instance
- You need to share a single DocMirror instance across multiple clients

## Programmatic Usage

```typescript
import { runMcpServer } from "./dist/index.js";

// Subprocess mode
await runMcpServer({ mode: "subprocess" });

// API mode
await runMcpServer({
  mode: "api",
  apiUrl: "http://localhost:8000",
});
```

## Development

```bash
# Install dependencies
npm install

# Build TypeScript
npm run build

# Run locally
npm start

# Run with API mode
npm start -- --api-url http://localhost:8000
```

## Publishing

Publishing is intentionally disabled. See [PUBLISH.md](./PUBLISH.md) for the
conditions that must be met before the first registry release.

## License

Apache 2.0
