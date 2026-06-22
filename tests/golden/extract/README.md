# Golden expected outputs — extract track

This directory holds **expected JSON/YAML snapshots** for extract-track TQG cases (row preservation, oracle, column fidelity).

## Role vs `manifest.json`

| Artifact | Purpose |
|----------|---------|
| `../manifest.json` | Machine index of **all** TQG cases (all tracks), synced from `docmirror/configs/yaml/test/gates/*.yaml` |
| `extract/` | Human-oriented storage for extract-specific expected outputs (diff targets) |

Regenerate the index after adding gate cases:

```bash
python3 tools/sync_golden_manifest.py
```

Case definitions live in `docmirror/configs/yaml/test/gates/extract.yaml` — not in this folder.
