# Golden expected outputs — edition track

This directory holds **expected DEC/community/enterprise JSON** snapshots for edition-track TQG cases.

## Role vs `manifest.json`

| Artifact | Purpose |
|----------|---------|
| `../manifest.json` | Machine index of **all** TQG cases (all tracks), synced from `docmirror/configs/yaml/test/gates/*.yaml` |
| `edition/` | Human-oriented storage for edition-specific expected outputs |

Regenerate the index after adding gate cases:

```bash
python3 tools/sync_golden_manifest.py
```

Case definitions live in `docmirror/configs/yaml/test/gates/edition.yaml` — not in this folder.
