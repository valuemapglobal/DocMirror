# DocMirror Java SDK

Java client SDK for the [DocMirror](https://docmirror.dev) Universal Document Parsing API.

Parse PDFs, images, and Office documents into structured DMIR (DocMirror Intermediate Representation)
— a lossless, framework-agnostic format designed for LLM ingestion, RAG pipelines, and document AI workflows.

## Features

- **Full DMIR type coverage** — Complete Java POJOs with Jackson annotations for all response types
- **Multiple input modes** — Parse from file path, raw bytes, or server-side files
- **Batch processing** — Upload and parse multiple files in a single request
- **Parse mode control** — Choose accuracy level: `auto`, `fast`, `balanced`, `accurate`
- **Bearer auth** — Simple API key authentication
- **OkHttp under the hood** — Robust HTTP client with connection pooling and timeouts

## Installation

### Maven

```xml
<dependency>
    <groupId>com.docmirror</groupId>
    <artifactId>docmirror-sdk</artifactId>
    <version>0.1.0</version>
</dependency>
```

### Gradle

```groovy
implementation 'com.docmirror:docmirror-sdk:0.1.0'
```

### Manual JAR

Download the latest JAR from [GitHub Releases](https://github.com/valuemapglobal/docmirror/releases).

## Quick Start

```java
import com.docmirror.sdk.DocMirrorClient;
import com.docmirror.sdk.DMIRResponse;
import com.docmirror.sdk.HealthResponse;

public class Example {
    public static void main(String[] args) throws Exception {
        DocMirrorClient client = new DocMirrorClient(
            "https://api.docmirror.dev",
            "sk-your-api-key"
        );

        // Parse a document
        DMIRResponse result = client.parseDocument("statement.pdf");
        System.out.println("Document type: " + result.getDocument().getType());
        System.out.println("Tables found: " + result.getDocument().getPages().get(0).getTables().size());

        // Health check
        HealthResponse health = client.health();
        System.out.println("Status: " + health.getStatus());
        System.out.println("Healthy: " + health.isHealthy());
    }
}
```

## API Reference

### `DocMirrorClient`

#### Constructors

| Constructor | Description |
|-------------|-------------|
| `new DocMirrorClient(baseUrl)` | Create with base URL only |
| `new DocMirrorClient(baseUrl, apiKey)` | Create with base URL and API key |
| `new DocMirrorClient(baseUrl, apiKey, httpClient)` | Create with full control over OkHttpClient |

#### `parseDocument(filePath)`

Parse a document from a local file path.

```java
DMIRResponse result = client.parseDocument("invoice.pdf");
```

#### `parseDocument(filePath, mode)`

Parse with explicit parse mode.

```java
DMIRResponse result = client.parseDocument("scan.pdf", "accurate");
```

#### `parseDocument(byte[] data, fileName)`

Parse from raw bytes (e.g. downloaded from an API, fetched from S3, etc.).

```java
byte[] pdfBytes = downloadFromS3("bucket/key");
DMIRResponse result = client.parseDocument(pdfBytes, "document.pdf");
```

#### `parseDocument(byte[] data, fileName, mode)`

Parse from raw bytes with explicit mode.

```java
DMIRResponse result = client.parseDocument(pdfBytes, "document.pdf", "forensic");
```

#### `parseDocumentBatch(String[] filePaths)`

Parse multiple documents in a single batch request.

```java
DMIRResponse result = client.parseDocumentBatch(new String[]{
    "invoice_001.pdf",
    "invoice_002.pdf",
    "report.pdf",
});
```

#### `parseDocumentBatch(String[] filePaths, String mode)`

Batch parse with explicit mode.

```java
DMIRResponse result = client.parseDocumentBatch(filePaths, "balanced");
```

#### `parseFileOnServer(String serverPath)`

Parse a file already present on the DocMirror server filesystem (no upload needed).

```java
DMIRResponse result = client.parseFileOnServer("/data/uploads/contract.pdf");
```

#### `parseFileOnServer(String serverPath, String mode)`

Parse a server-side file with explicit mode.

```java
DMIRResponse result = client.parseFileOnServer("/data/uploads/contract.pdf", "accurate");
```

#### `health()`

Check the API health.

```java
HealthResponse health = client.health();
if (health.isHealthy()) {
    System.out.println("API is healthy — version " + health.getVersion());
}
```

### Response Types

#### `DMIRResponse`

Top-level response wrapping all sections of the DMIR output.

| Method | Returns | Description |
|--------|---------|-------------|
| `getDmirVersion()` | `String` | DMIR schema version |
| `getDocument()` | `DocumentSection` | Document-level section with pages, properties |
| `getQuality()` | `QualitySection` | Parse confidence, trust score, validation |
| `getEvidence()` | `EvidenceSection` | Evidence provenance ledger |
| `getMeta()` | `MetaSection` | Parser diagnostics (elapsed ms, page/table/row counts) |

#### `HealthResponse`

| Method | Returns | Description |
|--------|---------|-------------|
| `getStatus()` | `String` | Server status |
| `getVersion()` | `String` | API version |
| `getTimestamp()` | `String` | ISO 8601 UTC timestamp |
| `isHealthy()` | `boolean` | Convenience check for `"ok"` or `"healthy"` status |

See [`DMIRResponse.java`](src/main/java/com/docmirror/sdk/DMIRResponse.java) for all nested types including `PageSection`, `TableBlock`, `DataRow`, `CellValue`, `KeyValuePair`, and the inner classes of `QualitySection` and `EvidenceSection`.

### Error Handling

All methods throw `java.io.IOException` on network errors or API errors. Error messages include the HTTP status code and server response body:

```java
try {
    DMIRResponse result = client.parseDocument("missing.pdf");
} catch (IOException e) {
    // e.getMessage() -> "DocMirror API error: HTTP 422 - File not found"
    System.err.println("API error: " + e.getMessage());
}
```

## Examples

### Custom HTTP Client Configuration

```java
OkHttpClient customClient = new OkHttpClient.Builder()
    .connectTimeout(10, TimeUnit.SECONDS)
    .readTimeout(300, TimeUnit.SECONDS)    // longer for large documents
    .writeTimeout(300, TimeUnit.SECONDS)
    .connectionPool(new ConnectionPool(5, 30, TimeUnit.SECONDS))
    .build();

DocMirrorClient client = new DocMirrorClient(
    "https://api.docmirror.dev",
    "sk-...",
    customClient
);
```

### Parsing from InputStream

```java
// Download from URL and parse directly
InputStream is = new URL("https://example.com/doc.pdf").openStream();
byte[] data = is.readAllBytes();

DMIRResponse result = client.parseDocument(data, "downloaded.pdf", "accurate");
System.out.printf("Document type: %s, %d pages%n",
    result.getDocument().getType(),
    result.getDocument().getPages().size());
```

## SDK Design

The Java SDK is **hand-written** for ergonomic Java usage patterns:

1. **Jackson-annotated POJOs** — Clean serialization/deserialization with `@JsonIgnoreProperties(ignoreUnknown = true)` for forward compatibility
2. **OkHttp** — Industry-standard HTTP client with connection pooling, timeouts, and interceptors
3. **Multiple file input paths** — File path, raw bytes, and server-side file parsing
4. **Convenience overloads** — Every method has a `mode` overload for explicit parse control
5. **`isHealthy()` convenience** — Quick check on `HealthResponse`

## Development

```bash
# Compile
mvn compile

# Run tests (requires a running DocMirror instance)
mvn test

# Package
mvn package

# Install to local Maven repository
mvn install
```

## License

Apache 2.0
