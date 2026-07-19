# Contributing to DocMirror SDKs

> One spec, four languages, infinite possibilities.

DocMirror maintains hand-written SDKs in **TypeScript**, **Go**, and **Java**, plus an **MCP Server** npm package.
All SDKs implement the same DMIR schema derived from the FastAPI contract. Release workflows generate the OpenAPI artifact at `docs/openapi/openapi.json`.

## SDK Structure

```
sdks/
├── typescript/       # @docmirror/sdk — source preview, not on npm
│   ├── src/
│   │   ├── client.ts    # DocMirrorClient — typed HTTP client
│   │   ├── types.ts     # DMIR type definitions (ParseResponse, DocumentSection, etc.)
│   │   └── index.ts     # Barrel exports
│   ├── package.json
│   └── tsconfig.json
├── go/               # Go source preview, no standalone repository yet
│   ├── client.go     # Client — typed HTTP client
│   ├── types.go      # DMIR Go struct definitions
│   ├── go.mod
│   └── README.md
├── java/             # com.docmirror:docmirror-sdk — source preview
│   └── src/main/java/com/docmirror/sdk/
│       ├── DocMirrorClient.java  # Typed HTTP client
│       ├── DMIRResponse.java     # DMIR POJOs with Jackson annotations
│       └── HealthResponse.java   # Health check response
└── mcp-server/       # @docmirror/mcp-server — source preview, not on npm
    └── src/
        ├── index.ts   # MCP server with subprocess + API modes
        └── cli.ts     # CLI entry point
```

## How SDKs Relate to the OpenAPI Spec

All SDKs implement the same DMIR (DocMirror Intermediate Representation) schema:

1. The canonical schema is defined by the FastAPI app at `docmirror/server/api.py`
2. `scripts/generate_openapi.py` generates `docs/openapi/openapi.json` as the release artifact for SDK checks
3. SDKs are **hand-written**, not auto-generated — giving each language idiomatic patterns
4. When the API contract changes, SDKs must be updated manually to match

This means: **one API change -> one generated spec check -> each SDK team updates their client**.

### Adding a New Language SDK

1. Create `sdks/<lang>/` directory with package manager config (package.json, go.mod, pom.xml, etc.)
2. Implement the four core methods: `parseDocument`, `parseDocumentBatch`, `parseFileOnServer`, `health`
3. Define DMIR types matching the OpenAPI spec schema
4. Write comprehensive README.md with installation and usage examples
5. Add the package to the distribution status table in this file
6. Open a PR with the new SDK

## Core API Surface (All SDKs)

Every SDK must implement these four operations:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `parseDocument(file, opts?)` | `POST /v1/parse` | Upload and parse a single document |
| `parseDocumentBatch(files[], opts?)` | `POST /v1/parse/batch` | Upload and parse multiple documents |
| `parseFileOnServer(path, opts?)` | `POST /v1/parse/file` | Parse a file on the server |
| `health()` | `GET /health` | Check API health |

### ParseOptions (shared across SDKs)

| Option | Type | Description |
|--------|------|-------------|
| `mode` | string | `auto`, `fast`, `balanced`, `accurate`, `forensic` |
| `edition` | string | `community`, `enterprise`, `finance`, `all` |
| `pages` | string | Page ranges: `"1-3,8,10-"` |
| `max_pages` | int | Max pages to parse |
| `workers` | int/string | Worker budget |
| `include_text` | bool | Include full markdown text |
| `include_geometry` | bool | Include table/cell geometry |
| `format` | string | Requested output format |
| `doc_type_hint` | string | Manual document type hint |

## Error Handling Conventions

Each SDK should provide typed/tagged error types for API failures:

- **TypeScript**: `DocMirrorApiError` with `statusCode` and `response` properties
- **Go**: Descriptive errors prefixed with `docmirror:` using `fmt.Errorf("docmirror: ...: %w", err)`
- **Java**: `IOException` subclass or typed exception with HTTP status code
- **MCP Server**: `isError: true` in MCP tool responses with descriptive messages

## Contribution Guidelines

### For Any SDK
- Keep source files clean and well-documented with language-appropriate doc comments
- Implement the four core operations with consistent parameter ordering
- Handle all documented `ParseOptions` fields (omit unsupported ones gracefully)
- Add integration tests that run against a live DocMirror API
- Keep `README.md` up to date with any new features or changed signatures
- Bump the SDK version for any API contract changes

### For TypeScript SDK
- Core client: `src/client.ts`, types: `src/types.ts`, exports: `src/index.ts`
- Tests go in `src/__tests__/`
- Build with `npm run build` (compiles `tsc` to `dist/`)
- Type-check with `npm run typecheck` (`tsc --noEmit`)

### For MCP Server
- MCP server logic in `src/index.ts`, CLI in `src/cli.ts`
- Each tool definition must include a descriptive JSON Schema
- Test subprocess mode by installing the Python `docmirror` package locally
- Build with `npm run build`

### For Go SDK
- Core client in `client.go`, types in `types.go`
- Uses only Go standard library — no external dependencies
- Tests go in `client_test.go`
- Build with `go build ./...`

### For Java SDK
- Client in `DocMirrorClient.java`, types in `DMIRResponse.java` and `HealthResponse.java`
- Uses OkHttp for HTTP and Jackson for JSON
- Tests go in `src/test/java/com/docmirror/sdk/`
- Build with `mvn compile`

## PR Process

1. If the API contract changed, regenerate and inspect the OpenAPI artifact with `python scripts/generate_openapi.py`
2. Update any affected SDK methods or types to match
3. Add or update tests for your change
4. Bump the SDK version if the API contract or public API surface changed:
   - TypeScript/MCP: `package.json` `version` field
   - Go: `go.mod` module path or version tag
   - Java: `pom.xml` `<version>`
5. Verify compilation: `npm run build`, `go build ./...`, or `mvn compile` respectively
6. Request review from the DocMirror core team

## Distribution Status

All four SDK surfaces are previews. None is currently published to a registry,
and `.github/workflows/publish-sdks.yml` performs build validation only.

| Package identity | Intended registry | Current status |
|------------------|-------------------|----------------|
| `@docmirror/sdk` | npm | Not published; source preview only |
| Go SDK | Go proxy | No standalone module repository; source preview only |
| `com.docmirror:docmirror-sdk` | Maven Central | Not published; source preview only |
| `@docmirror/mcp-server` | npm | Not published; source preview only |

## License

All SDK packages are Apache 2.0 licensed. By contributing, you agree to license your contributions under the same license.
