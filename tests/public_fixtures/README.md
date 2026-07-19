# Public synthetic fixtures

This directory contains source-controlled generators for test inputs that are
safe to use in public CI. Generated binary documents are written below
`generated/` and are intentionally not committed.

All content produced here must be synthetic, contain no customer information,
and be reproducible from a clean checkout. Generate the fixtures with:

```bash
python -m tests.public_fixtures.generate
```

`tests/fixtures/` remains a legacy mixed directory. TQG treats inputs from that
directory as private by default; new public binary inputs belong here as tracked
generators instead.
