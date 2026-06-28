# @docmirror/sdk

Typed TypeScript client for the [DocMirror](https://docmirror.dev) Universal Document Parsing API.

Parse PDFs, images, and Office documents into structured DMIR (DocMirror Intermediate Representation) — a lossless, framework-agnostic format designed for LLM ingestion, RAG pipelines, and document AI workflows.

## Features

- **Full DMIR type coverage** — All response types, quality metrics, evidence tracking
- **Zero-cost HTTP** — Uses native `fetch` (Node.js 18+ / modern browsers) with no heavyweight HTTP library
- **Batch processing** — Upload and parse multiple files in a single request
- **Server-side parsing** — Parse files already on the DocMirror server
- **Configurable timeout** — Per-request timeout with `AbortController`
- **Bearer auth** — Simple API key authentication
- **Error typing** — `DocMirrorApiError` with HTTP status code and parsed response body
- **Isomorphic** — Works in Node.js and browser environments

## Installation

```bash
npm install @docmirror/sdk
```

## Quick Start

```typescript
import { DocMirrorClient } from "@docmirror/sdk";

const client = new DocMirrorClient({
  apiKey: "sk-your-api-key",
  baseUrl: "https://api.docmirror.dev",   // optional, defaults to http://localhost:8000
});

// Parse a document
const result = await client.parseDocument("statement.pdf");
console.log(result.data?.document?.type);
console.log(result.data?.document?.pages?.[0]?.tables);

// Health check
const health = await client.health();
console.log(health.status);
```

## API Reference

### `DocMirrorClient`

#### Constructor

```typescript
new DocMirrorClient(config?: DocMirrorClientConfig)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config.baseUrl` | `string` | `http://localhost:8000` | API base URL |
| `config.apiKey` | `string` | — | Bearer auth token |
| `config.timeoutMs` | `number` | `120000` | Request timeout (ms) |
| `config.fetch` | `typeof fetch` | `globalThis.fetch` | Custom fetch implementation |

#### `parseDocument(filePath, options?)`

Parse a single document file.

```typescript
client.parseDocument(filePath: string | File | Blob, options?: ParseOptions): Promise<ParseResponse>
```

- **Node.js**: Pass a file path string (reads the file with `fs.readFile`)
- **Browser**: Pass a `File` or `Blob` object

#### `parseDocumentBatch(filePaths, options?)`

Parse multiple documents in a single batch request.

```typescript
client.parseDocumentBatch(filePaths: (string | File | Blob)[], options?: ParseOptions): Promise<ParseResponse[]>
```

#### `parseFileOnServer(serverPath, options?)`

Parse a file that already exists on the DocMirror server filesystem.

```typescript
client.parseFileOnServer(serverPath: string, options?: ParseOptions): Promise<ParseResponse>
```

#### `health()`

Check the API health status.

```typescript
client.health(): Promise<HealthResponse>
```

### `ParseOptions`

| Option | Type | Description |
|--------|------|-------------|
| `mode` | `string` | Parse mode: `"auto"`, `"fast"`, `"balanced"`, `"accurate"`, `"forensic"` |
| `edition` | `string` | Output edition: `"community"`, `"enterprise"`, `"finance"`, `"all"` |
| `pages` | `string` | Page ranges (e.g. `"1-3,8,10-"`) |
| `max_pages` | `number` | Maximum pages to parse |
| `workers` | `number \| string` | Worker budget |
| `include_text` | `boolean` | Include full markdown text |
| `include_geometry` | `boolean` | Include table/cell geometry |
| `format` | `string` | Output format |
| `doc_type_hint` | `string` | Document type hint |

### Response Types

#### `ParseResponse`

| Field | Type | Description |
|-------|------|-------------|
| `code` | `number` | HTTP status code |
| `message` | `string` | `"success"` or `"error"` |
| `api_version` | `string` | API version |
| `request_id` | `string` | Tracing UUID |
| `timestamp` | `string` | ISO 8601 UTC |
| `data` | `ParseResultData \| null` | DMIR payload (on success) |
| `error` | `ApiError \| null` | Error details (on failure) |
| `meta` | `Record<string, unknown> \| null` | Parser diagnostics |

See the [full type definitions](./src/types.ts) for complete DMIR schema details including `DocumentSection`, `PageSection`, `TableBlock`, `QualitySection`, and `EvidenceSection`.

### Error Handling

```typescript
import { DocMirrorClient, DocMirrorApiError } from "@docmirror/sdk";

const client = new DocMirrorClient({ apiKey: "sk-..." });

try {
  const result = await client.parseDocument("unknown.pdf");
} catch (error) {
  if (error instanceof DocMirrorApiError) {
    console.error(`API Error [${error.statusCode}]: ${error.message}`);
    // error.response contains the parsed API response, if available
  }
}
```

`DocMirrorApiError` properties:

| Property | Type | Description |
|----------|------|-------------|
| `statusCode` | `number` | HTTP status (0 for network errors) |
| `message` | `string` | Error description |
| `response` | `ParseResponse \| undefined` | Parsed API response body |

## Examples

### Browser Usage

```typescript
import { DocMirrorClient } from "@docmirror/sdk";

const client = new DocMirrorClient({ baseUrl: "https://api.docmirror.dev" });

// Handle file input
document.querySelector("input[type=file]")?.addEventListener("change", async (e) => {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (!file) return;

  const result = await client.parseDocument(file);
  console.log(`Document type: ${result.data?.document?.type}`);
});
```

### Batch Processing

```typescript
const results = await client.parseDocumentBatch([
  "invoice_001.pdf",
  "invoice_002.pdf",
  "report.pdf",
]);

for (const result of results) {
  if (result.data?.document) {
    console.log(`Parsed ${result.data.document.type}: ${result.data.document.pages?.length} pages`);
  }
}
```

### Server-Side File

```typescript
// Parse a file already uploaded to the server
const result = await client.parseFileOnServer("/data/uploads/contract.pdf", {
  mode: "accurate",
});
```

## TypeScript SDK Design

The SDK is **hand-written** for ergonomics, not auto-generated. It provides:

1. **Type-safe API surface** — Full TypeScript interfaces for all DMIR types
2. **Isomorphic file handling** — File path resolution in Node.js, direct Blob/File in browser
3. **Native `fetch`** — No heavyweight HTTP client dependency; works with any fetch-compatible polyfill
4. **Clean error model** — `DocMirrorApiError` with typed cause

To regenerate the OpenAPI spec (for reference):

```bash
npm run generate
```

## License

Apache 2.0
