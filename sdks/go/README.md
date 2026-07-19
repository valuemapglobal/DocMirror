# DocMirror Go SDK

> **Preview status:** this module is source-only in the DocMirror monorepo. It
> has no versioned Go module release and is not available through the Go proxy.

Go client SDK for the [DocMirror](https://valuemapglobal.github.io/DocMirror/) Universal Document Parsing API.

Parse PDFs, images, and Office documents into structured DMIR (DocMirror Intermediate Representation)
— a lossless, framework-agnostic format for LLM ingestion, RAG pipelines, and document AI.

## Features

- **Zero external dependencies** — Uses only Go standard library (`net/http`, `mime/multipart`)
- **Full DMIR type support** — Complete Go structs for all response types
- **Batch processing** — Upload and parse multiple files in a single request
- **Server-side parsing** — Parse files already on the DocMirror server
- **Configurable HTTP client** — Pass your own `*http.Client` for custom timeouts, transports
- **Bearer auth** — Simple API key authentication

## Preview Build

```bash
git clone https://github.com/valuemapglobal/DocMirror.git
cd DocMirror/sdks/go
go test ./...
```

The public hosted API is not available yet. Run or deploy DocMirror yourself
and point the client at that base URL; local examples use `http://localhost:8000`.

## Quick Start

```go
package docmirror

func example() error {
    client := NewClient("http://localhost:8000", "sk-your-api-key")

    // Parse a single document
    result, err := client.ParseDocument("statement.pdf", nil)
    if err != nil {
        return err
    }

    println("Document type:", result.Data.Document.Type)
    println("Pages:", len(result.Data.Document.Pages))

    // Check API health
    health, err := client.Health()
    if err != nil {
        return err
    }
    println("API status:", health.Status, "version:", health.Version)
    return nil
}
```

This in-package example is intended for evaluating the checked-out preview;
there is no released module version to install yet.

## API Reference

### `Client`

#### `NewClient(baseURL, apiKey string) *Client`

Create a new DocMirror API client with default timeout (120s).

#### `NewClientWithHTTP(baseURL, apiKey string, httpClient *http.Client) *Client`

Create a new client with a custom `*http.Client` for fine-grained control over timeouts, transports, and proxies.

#### `ParseDocument(filePath string, opts *ParseOptions) (*ParseResponse, error)`

Upload and parse a single document file.

```go
result, err := client.ParseDocument("invoice.pdf", &docmirror.ParseOptions{
    Mode: "accurate",
})
```

#### `ParseDocumentBatch(filePaths []string, opts *ParseOptions) (*ParseResponse, error)`

Upload and parse multiple documents in batch.

```go
results, err := client.ParseDocumentBatch([]string{
    "invoice1.pdf",
    "invoice2.pdf",
    "report.pdf",
}, &docmirror.ParseOptions{
    Mode: "balanced",
})
```

#### `ParseFileOnServer(serverPath string, opts *ParseOptions) (*ParseResponse, error)`

Parse a file already present on the DocMirror server filesystem (no upload needed).

```go
result, err := client.ParseFileOnServer("/data/uploads/contract.pdf", &docmirror.ParseOptions{
    Mode: "accurate",
})
```

#### `Health() (*HealthResponse, error)`

Check the API health status.

```go
health, err := client.Health()
if err != nil {
    log.Fatal(err)
}
fmt.Printf("Status: %s\n", health.Status)
```

### `ParseOptions`

| Field | Type | Description |
|-------|------|-------------|
| `Mode` | `string` | Parse mode: `"auto"`, `"fast"`, `"balanced"`, `"accurate"`, `"forensic"` |
| `Edition` | `string` | Output edition: `"community"`, `"enterprise"`, `"finance"`, `"all"` |
| `Pages` | `string` | Page ranges (e.g. `"1-3,8,10-"`) |
| `MaxPages` | `int` | Maximum pages to parse |
| `Workers` | `string` | Worker budget |
| `IncludeText` | `bool` | Include full markdown text |
| `IncludeGeometry` | `bool` | Include table/cell geometry |
| `Format` | `string` | Output format |
| `DocTypeHint` | `string` | Manual document type hint |

### Response Types

The SDK provides complete Go struct types under the `docmirror` package:

- `ParseResponse` — Top-level API response envelope
- `ParseResultData` — DMIR business payload
- `DocumentSection` — Document-level section with pages, properties, full text
- `PageSection` — Page contents: text blocks, tables, key-value pairs
- `TableBlock` — Extracted tables with headers and data rows
- `QualitySection` — Parse confidence, trust score, validation
- `EvidenceSection` — Evidence provenance ledger
- `HealthResponse` — Health check response

See [`types.go`](./types.go) for the complete schema.

### Error Handling

The SDK returns Go errors with descriptive messages prefixed with `docmirror:`. API errors include the HTTP status code and error detail:

```go
result, err := client.ParseDocument("missing.pdf", nil)
if err != nil {
    // err.Error() -> "docmirror: API error (HTTP 422): File not found"
    fmt.Println(err)
}
```

## Examples

### Custom HTTP Client

```go
transport := &http.Transport{
    MaxIdleConns:    10,
    IdleConnTimeout: 30 * time.Second,
}
httpClient := &http.Client{
    Timeout:   30 * time.Second,
    Transport: transport,
}

client := docmirror.NewClientWithHTTP("http://localhost:8000", "sk-...", httpClient)
```

### Parsing with Explicit Options

```go
result, err := client.ParseDocument("scan.pdf", &docmirror.ParseOptions{
    Mode:            "forensic",
    IncludeGeometry: true,
    Pages:           "1-5",
})
if err != nil {
    log.Fatal(err)
}

for _, page := range result.Data.Document.Pages {
    fmt.Printf("Page %d: %d text blocks, %d tables\n",
        page.PageNumber, len(page.Texts), len(page.Tables))
}
```

## SDK Design

The Go SDK is **hand-written** for ergonomic Go usage patterns. Key design decisions:

1. **Standard library only** — No external HTTP or JSON dependencies
2. **Explicit `*http.Client` injection** — Users can configure timeouts, TLS, proxies
3. **Canonical Go types** — `time.Time` for timestamps, `float64` for dimensions/confidence
4. **Clean error wrapping** — All errors include context with `fmt.Errorf("docmirror: ...: %w", err)`

## Development

```bash
# Build
go build ./...

# Test
go test ./...

# Vet
go vet ./...
```

## License

Apache 2.0
