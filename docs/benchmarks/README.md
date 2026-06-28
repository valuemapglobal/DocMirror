# Benchmarks

DocMirror public benchmark artifacts must be reproducible from public inputs.

For OSS 1.0.0, the public mini benchmark is intentionally synthetic and
dependency-light:

```bash
python scripts/run_first_benchmark.py --public-mini
python scripts/generate_benchmark_table.py --public-mini
```

It measures evidence/trust contract coverage from
`examples/fixtures/trust_quickstart_artifact.json`. Private fixture benchmarks
may exist in internal release workflows, but public README claims should only
use numbers that can be regenerated from public files.
