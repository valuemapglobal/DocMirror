# ADR 0003: P1 core stability qualification

- Status: Accepted
- Date: 2026-07-23
- Depends on: ADR 0002

## Decision

P1 adds no production node or alternate data path. The qualified runtime is:

```text
AcceptedSource + ParsePolicy -> Dispatcher -> Adapter -> Canonical Pipeline
  -> Validation -> Seal
  -> SealedParseResult
  -> Mirror + unified Post-Seal PluginRegistry
  -> Community / Enterprise / Finance projectors
  -> ArtifactWriter
```

## Qualification invariants

1. The Canonical Pipeline has no plugin dependency or plugin-controlled stage.
2. Seven bundled Community projectors and optional external projectors execute
   only through the unified Post-Seal PluginRegistry.
3. Runtime timing, paths, worker counts, licensing, diagnostics, and delivery
   metadata do not participate in the fact fingerprint.
4. Every projector starts from the same sealed snapshot.
5. External provider code is not imported during parsing.
6. Plugin installation, absence, failure, timeout, entitlement, and schema
   incompatibility cannot change Core facts.

## Formal stability gates

- frozen semantic Core contract fingerprint;
- mandatory 6+1 real/desensitized-real Golden cases;
- forced-hint and automatic-classification coverage;
- identical fact fingerprints across the approved worker matrix;
- approved long-document performance and RSS baselines;
- post-seal projector failure and timeout isolation;
- clean-environment external projector build/install/discover/project/write E2E;
- installed/uninstalled and licensed/unlicensed fact-fingerprint invariance.

Qualification is evidence-based for the exact candidate. A Core contract
change invalidates the candidate immediately and requires regeneration of all
technical evidence. Publication requires successful CI for the exact release
commit.
