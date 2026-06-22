# Golden expected outputs — classify track

This directory holds **expected classification snapshots** (e.g. `document_type` baselines) for classify-track TQG cases.

## Role vs `manifest.json`

| Artifact | Purpose |
|----------|---------|
| `../manifest.json` | Machine index of **all** TQG cases (all tracks), synced from `docmirror/configs/yaml/test/gates/*.yaml` |
| `classify/` | Human-oriented storage for classify-specific expected outputs |

Regenerate the index after adding gate cases:

```bash
python3 scripts/sync/sync_golden_manifest.py
```

Case definitions live in `docmirror/configs/yaml/test/gates/classify.yaml` — not in this folder.
