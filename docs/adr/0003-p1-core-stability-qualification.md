# ADR 0003: P1 core stability qualification

- Status: Accepted
- Date: 2026-07-23
- Depends on: ADR 0002

## Decision

P1 adds no production node or alternate data path. The qualified runtime is:

```text
AcceptedSource + ParsePolicy -> Dispatcher -> Adapter -> Canonical Pipeline
  -> fixed Core canonical enrichment -> Validation -> Seal
  -> SealedParseResult
  -> Core projectors and optional post-seal plugin projectors
  -> ArtifactWriter
```

## Qualification invariants

1. Seven bundled canonical capabilities produce private `CanonicalPatch`
   values and are selected from a fixed Core inventory.
2. Patch application is transactional; validation or application failure
   leaves the caller-owned result unchanged.
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
