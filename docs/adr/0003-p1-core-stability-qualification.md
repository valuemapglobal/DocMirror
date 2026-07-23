# ADR 0003: P1 core stability qualification

- Status: Accepted
- Date: 2026-07-22
- Depends on: ADR 0002

## Decision

P1 does not add a production node or data path. The normative runtime remains:

```text
AcceptedSource + ParsePolicy -> Dispatcher -> Adapter -> Canonical Assembly
  -> generic Normalize / Structure / Entity
  -> DomainRecognizer -> FactPatch
  -> Canonical Validation + Mutation Audit
  -> seal() -> SealedParseResult
  -> sibling Mirror / Community / Enterprise / Finance projectors
  -> ArtifactWriter
```

Contract freeze, 6+1 Golden, worker determinism, plugin chaos, performance/RSS,
external-plugin installation, and evidence aggregation are CI/release controls.
They never become canonical facts and never write to `ParseResult`.

## Pre-observation invariants

1. Every bundled recognizer returns `FactPatch` directly. An edition envelope is
   not adapted into facts.
2. Applying a patch is transactional: validation or application failure leaves
   the caller-owned canonical result unchanged.
3. Snapshot integrity and fact determinism use distinct fingerprints. Runtime
   timing, paths, worker counts, licensing, diagnostics, and delivery metadata
   are excluded from the fact digest.
4. Every projector starts from the sealed result and cannot change another
   projector's view or the immutable snapshot.
5. Plugin absence, failure, timeout, and lack of entitlement cannot change core
   facts. Runtime diagnostics stay outside the fact model.

## Formal stability gates

- a frozen semantic core-contract fingerprint for the exact candidate;
- mandatory 6+1 real/desensitized-real Golden cases, with no missing-fixture skip;
- identical fact fingerprints across the approved worker matrix;
- approved long-document p50/p95, peak RSS, timeout, and OOM baselines;
- plugin chaos invariants for recognizer and projector failures;
- a clean-environment external provider install requiring no core source change.

Qualification is evidence-based for the current candidate and has no calendar
waiting period or release-cycle counter. A core contract change invalidates the
candidate immediately and requires all technical gates to be regenerated for
the new fingerprint. Publication still requires successful CI for the exact
release commit.
