# Frozen Golden Snapshots (Do Not Edit)
This directory stores immutable frozen golden benchmark outputs for GA releases.
Each version subdirectory is a snapshot that must never be modified after creation.

## Structure
- `manifest.json` — snapshot index (fixture_id → frozen output path)
- `{domain}/` — per-domain frozen output JSON files

## Freezing
Run: `python tools/freeze_golden.py`

## Drift Detection
Run: `python tools/generate_domain_drift_report.py --compare-frozen ga-1.0`

