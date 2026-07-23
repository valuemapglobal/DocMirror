# Community schema migration: 2.2 to 3.0

Community 3.0 is DocMirror's current structured delivery contract. It is a
self-contained six-block document with complete Dataset rows:

```text
schema, document, sections, datasets, files, warnings
```

The former 2.2 edition envelope (`schema_version`, `edition`, `data`, etc.) is
not selected by inspecting payload shape. Code that intentionally validates or
exports that compatibility contract must request the explicit `community_v2`
schema. New integrations must use `community` 3.0.

Key migration rules:

- read business records from `datasets[].rows`, not arbitrary keys below
  `data`;
- use `record_id` as the stable primary key;
- verify `row_count == completeness.emitted_row_count == len(rows)`;
- use `sections[].dataset_refs` to connect narrative structure and datasets;
- use `files` for companion Markdown/CSV locations;
- read schema identity from `schema.name` and `schema.version`.

Artifact manifests publish the version of every projection schema. A future
breaking Community change requires a new major schema name/version, a migration
guide, consumer fixtures, and an explicit compatibility exporter decision.
