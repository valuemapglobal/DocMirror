# ADR 0001: Community JSON is a self-contained structured API

- Status: Accepted
- Date: 2026-07-21

## Decision

`<file_id>_community.json` is the canonical, self-contained Community structured
API exchanged with upstream and downstream systems. Its six top-level blocks stay
stable, while every `datasets[]` entry embeds all business records in `rows`.

Each record has a stable `record_id`, `normalized`, `canonical_raw`, `raw`, and
`source`. Optional confidence and review information may be attached. Each Dataset
also publishes `completeness`, and no persisted Community JSON may use preview,
pagination, or truncation semantics.

`<file_id>_content.md` is the complete human review projection. Dataset CSVs are
parallel, analysis-oriented projections. JSON and CSV are rendered from the same
Dataset snapshot and must preserve identical ordered record IDs.

## Invariants

For every Dataset:

```text
row_count
= completeness.emitted_row_count
= len(rows)
= companion CSV data-row count
```

`record_id` values are present and unique, and their order is identical in JSON
and CSV. When an independent physical count is available, it becomes
`completeness.expected_row_count`; any difference is visible as `partial` with a
non-zero omission count.

## Consequences

Consumers can use Community JSON without opening companion files. Markdown and
CSV remain first-class outputs for their distinct review and analysis use cases.
The artifact is larger than a row-free index, but correctness and interoperability
take priority; transport compression belongs at the HTTP or storage layer.
