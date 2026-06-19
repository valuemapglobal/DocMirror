# Quality Gate — DocMirror

**One script** for all code-quality scans: hygiene audit and pre-production release checks.

```bash
python scripts/run_quality_gate.py --list-steps
```

## Profiles

| Profile | Command | Use when |
|---------|---------|----------|
| `hygiene` | `--profile hygiene --strict` | Dead code / orphans only (CI hygiene job) |
| `quick` | `--profile quick` | Local edit loop (~1–3 min) |
| `standard` | *(default)* | Before push / PR (~8–20 min) |
| `full` | `--profile full` | Release candidate (~30+ min) |

## Examples

```bash
# Hygiene only (replaces run_hygiene_audit.py)
python scripts/run_quality_gate.py --profile hygiene --strict
python scripts/run_quality_gate.py --profile hygiene --only ruff_strict,vulture \
  --json reports/hygiene.json --markdown reports/hygiene.md

# Pre-production gate (replaces run_release_gate.py)
python scripts/run_quality_gate.py
python scripts/run_quality_gate.py --profile quick --stop-on-fail
python scripts/run_quality_gate.py --profile full \
  --json reports/release_gate.json --markdown reports/release_gate.md
```

Install dev dependencies for gate profiles: `pip install -e ".[dev]"`.

## Layers (standard / full)

1. **Style** — ruff format + lint
2. **Hygiene** — full strict audit ([design doc](../docs/design/25_code_hygiene_audit_program.md))
3. **Contracts** — FCR, DTI, MEP, post-extract, TQG, CPS layout
4. **Architecture** — god-file, PCM gates, core imports, import-linter
5. **Tests** — unit; + tier matrix + coverage (`full`)

Allowlist: `configs/hygiene/allowlist.yaml`
