# Error Handling

## Behavior on Failure

- When the pipeline fails (file not found, unsupported format, extraction error, etc.), DocMirror returns a **PerceptionResult** with `status=failure`, `error` set, and empty or partial `content`. It does **not** raise exceptions to the caller by default.
- There is **no automatic fallback** to "text-only" or "image-only" extraction when the full pipeline fails. A future option such as `fallback_on_full_failure: "text_only"` may be added to allow a second attempt that only extracts raw text.

## Error Codes and Recoverability

`PerceptionResult.error` is an **ErrorDetail** with:

| Field | Description |
|-------|-------------|
| `code` | Canonical error code (string). |
| `message` | Technical message (for logs / debugging). |
| `recoverable` | If `True`, the caller may retry after fixing the condition (e.g. installing LibreOffice for .doc). |

### Common Error Codes

| Code | Recoverable | Typical cause |
|------|-------------|----------------|
| `FILE_NOT_FOUND` | No | Path does not exist. |
| `FILE_TOO_SMALL` | No | File smaller than minimum size. |
| `FILE_TOO_LARGE` | No | File exceeds max size. |
| `FILE_EMPTY` | No | File is 0 bytes. |
| `UNSUPPORTED_FORMAT` | No | Format not supported by any adapter. |
| `FORMAT_REQUIRES_CONVERTER` | Yes | Legacy .doc requires LibreOffice (soffice). |
| `EXTRACTION_FAILED` | No | Core extraction failed. |
| `ORCHESTRATION_FAILURE` | No | Unhandled exception in the pipeline. |

Use `error.code` and `error.recoverable` to decide whether to show a user message or retry.

## "No Tables" vs Normal Documents

- **Table-dominant documents** (e.g. bank statements): If the pipeline expects tables (from pre-analysis) but finds none, status is set to **partial** and an error is added ("No tables found in document layout").
- **Text-dominant or mixed documents** with no tables: Status remains **success**; having zero tables is not treated as a failure.

This avoids false "partial" results for plain text or mixed documents that legitimately have no tables.
