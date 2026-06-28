/**
 * @docmirror/mcp-server — MCP (Model Context Protocol) server for DocMirror
 *
 * Exposes DocMirror's document parsing capabilities as MCP tools
 * for LLM clients (Claude Desktop, Cursor, Codex, etc.).
 *
 * Two operation modes:
 *   1. **Subprocess** (default) — Spawns the Python ``docmirror.server.mcp``
 *      as a child process and forwards MCP traffic via stdio passthrough.
 *   2. **REST API** (``--api-url``) — Calls the DocMirror REST API for each
 *      tool invocation. Useful when Python is not available on the host.
 *
 * @packageDocumentation
 */

import { spawn, type ChildProcess } from "node:child_process";
import process from "node:process";

// ── Defaults ──

const DEFAULT_API_URL = "http://localhost:8000";
const DEFAULT_PYTHON = "python3";

// ── Server Instance ──

export interface McpServerOptions {
  /** Operation mode */
  mode: "subprocess" | "api";
  /** DocMirror REST API base URL (used in API mode) */
  apiUrl?: string;
  /** Python executable (used in subprocess mode) */
  python?: string;
}

/**
 * Start the DocMirror MCP server.
 *
 * In **subprocess mode** (default), the Python DocMirror MCP server is spawned
 * as a child process and stdio is forwarded. The MCP client communicates
 * directly with the Python process.
 *
 * In **API mode** (``--api-url``), a native MCP server is started that calls
 * the DocMirror REST API for each tool invocation. This mode does not require
 * Python.
 *
 * @param options - Server configuration
 */
export async function runMcpServer(options: McpServerOptions): Promise<void> {
  if (options.mode === "subprocess") {
    await runSubprocessMode(options);
  } else {
    await runApiMode(options);
  }
}

// ── Subprocess Mode ──

async function runSubprocessMode(options: McpServerOptions): Promise<void> {
  const python = options.python ?? DEFAULT_PYTHON;
  const proc: ChildProcess = spawn(python, [
    "-m",
    "docmirror.server.mcp",
    "--transport",
    "stdio",
  ], {
    stdio: ["pipe", "pipe", "inherit"],
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
  });

  // Forward stdin/stdout between parent and child
  if (proc.stdin) {
    process.stdin.pipe(proc.stdin);
  }
  if (proc.stdout) {
    proc.stdout.pipe(process.stdout);
  }

  proc.on("exit", (code) => {
    process.exit(code ?? 0);
  });

  proc.on("error", (err) => {
    console.error("[docmirror-mcp] Failed to start Python subprocess:", err.message);
    process.exit(1);
  });
}

// ── API Mode ──

interface ToolDefinition {
  name: string;
  description: string;
  inputSchema: {
    type: "object";
    properties: Record<string, unknown>;
    required: string[];
  };
}

const TOOLS: ToolDefinition[] = [
  {
    name: "parse_document",
    description:
      "Parse a document file (PDF, image, Office) and return structured DMIR JSON. " +
      "DMIR (DocMirror Intermediate Representation) is a lossless, framework-agnostic format.",
    inputSchema: {
      type: "object",
      properties: {
        file_path: {
          type: "string",
          description: "Absolute or relative path to the document file.",
        },
        mode: {
          type: "string",
          enum: ["auto", "fast", "balanced", "accurate"],
          description: "Parse mode. 'auto' picks based on file type.",
        },
      },
      required: ["file_path"],
    },
  },
  {
    name: "parse_document_from_bytes",
    description:
      "Parse a document from raw bytes (e.g. from an API response) " +
      "and return structured DMIR JSON.",
    inputSchema: {
      type: "object",
      properties: {
        data: {
          type: "string",
          description: "Base64-encoded document bytes.",
        },
        filename: {
          type: "string",
          description: "Original filename with extension (e.g. 'statement.pdf').",
        },
        mode: {
          type: "string",
          enum: ["auto", "fast", "balanced", "accurate"],
          description: "Parse mode. 'auto' picks based on file type.",
        },
      },
      required: ["data", "filename"],
    },
  },
];

async function runApiMode(options: McpServerOptions): Promise<void> {
  const apiUrl = (options.apiUrl ?? DEFAULT_API_URL).replace(/\/+$/, "");

  // Dynamic import of the MCP SDK
  const { Server } = await import("@modelcontextprotocol/sdk/server/index.js");
  const { StdioServerTransport } = await import(
    "@modelcontextprotocol/sdk/server/stdio.js"
  );
  const {
    CallToolRequestSchema,
    ListToolsRequestSchema,
  } = await import("@modelcontextprotocol/sdk/types.js");

  const server = new Server(
    {
      name: "docmirror-mcp-server",
      version: "0.1.0",
    },
    {
      capabilities: {
        tools: {},
      },
    },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: TOOLS,
  }));

  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;

    try {
      switch (name) {
        case "parse_document": {
          const filePath = args?.file_path as string;
          if (!filePath) throw new Error("file_path is required");
          const mode = (args?.mode as string) ?? "auto";

          const url = new URL(`${apiUrl}/v1/parse/file`);
          url.searchParams.set("mode", mode);

          const response = await fetch(url.toString(), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: filePath }),
          });

          const result = await response.json();
          return {
            content: [
              {
                type: "text" as const,
                text: JSON.stringify(result, null, 2),
              },
            ],
          };
        }

        case "parse_document_from_bytes": {
          const data = args?.data as string;
          const filename = args?.filename as string;
          const mode = (args?.mode as string) ?? "auto";
          if (!data || !filename) throw new Error("data and filename are required");

          // Decode base64 and create a Blob
          const binaryStr = atob(data);
          const bytes = new Uint8Array(binaryStr.length);
          for (let i = 0; i < binaryStr.length; i++) {
            bytes[i] = binaryStr.charCodeAt(i);
          }
          const blob = new Blob([bytes]);

          const formData = new FormData();
          formData.append("file", blob, filename);
          formData.append("mode", mode);

          const url = new URL(`${apiUrl}/v1/parse`);

          const response = await fetch(url.toString(), {
            method: "POST",
            body: formData,
          });

          const result = await response.json();
          return {
            content: [
              {
                type: "text" as const,
                text: JSON.stringify(result, null, 2),
              },
            ],
          };
        }

        default:
          throw new Error(`Unknown tool: ${name}`);
      }
    } catch (error) {
      return {
        content: [
          {
            type: "text" as const,
            text: `Error: ${(error as Error).message}`,
          },
        ],
        isError: true,
      };
    }
  });

  const transport = new StdioServerTransport();
  await server.connect(transport);
}
