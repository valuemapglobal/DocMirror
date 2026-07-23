# ADR 0002: P0 canonical fact pipeline and sealed projection boundary

- Status: Accepted
- Date: 2026-07-22
- Supersedes: informal Architecture A pipeline descriptions

## Context

DocMirror has one factual result, but Community recognition historically produced
an edition-shaped payload and merged that payload back into `ParseResult`.
`ParseResult` also exposed Mirror serialization methods and remained mutable while
projectors executed.  Those compatibility paths made the intended boundary a
convention rather than an enforceable architecture.

## Decision

The P0 target pipeline is:

```text
AcceptedSource (content identity bound) + ParsePolicy
  -> Dispatcher
  -> Adapter (evidence and basic facts)
  -> Canonical Assembly
  -> generic Normalize / Structure / Entity
  -> DomainRecognizer.recognize() -> FactPatch
  -> validate/apply FactPatch + Mutation Audit
  -> seal_parse_result() -> SealedParseResult
  -> independent read-only projectors
  -> ArtifactWriter / API response
```

The following invariants are normative:

1. `AcceptedSource` binds the bytes consumed by the adapter to the checksum
   accepted at intake.  A mutable caller-owned path is not a content identity.
2. A recognizer never returns an edition envelope and never mutates
   `ParseResult`. It returns a validated, ephemeral `FactPatch`.
3. `FactPatch` is not a retained model or a second source of truth.  It is
   applied once inside the canonical mutation boundary and then discarded.
4. Conflicts are deterministic. Existing non-empty canonical scalar facts win
   unless the patch declares an explicit replacement and supplies provenance.
   Dataset record identifiers must be unique and stable.
5. Every applied fact change creates a mutation-audit entry identifying the
   provider, target, old value, new value, confidence, and reason.
6. `seal_parse_result()` creates an immutable content snapshot with no writable
   reference to the source `ParseResult`. Projectors receive isolated read views
   derived from this snapshot.
7. Mirror, Community, Enterprise, and Finance are sibling projectors. No
   projector may invoke recognition, consume another projector's payload, or
   write facts back into the sealed result.
8. `ArtifactWriter` owns persistence mechanics only. It must not recognize,
   repair, or interpret canonical business facts.
9. Built-in, commercial, and third-party extensions register through one
   provider registry. Entry-point/pluggy integration is discovery transport,
   not a second execution system.
10. DMIR remains an explicit exporter for MCP, PDF/UA, or an explicitly selected
    exporter. It is not an intermediate representation in the main pipeline.

## Plugin roles

A provider may contribute either or both roles, but the roles are independent:

- `DomainRecognizer`: reads a canonical read view and returns `FactPatch`.
- `EditionProjector`: reads a `SealedParseResult` snapshot and returns a delivery
  payload.

Licensing is checked at the projector/provider boundary. Licensing metadata is
never a canonical fact and is therefore excluded from `FactPatch`.

## Compatibility

Temporary forwarding APIs may materialize an isolated legacy `ParseResult` read
copy. They must be marked as compatibility shims, may not expose the mutable
canonical instance, and must have contract tests proving that mutations cannot
change the sealed fingerprint.

Community schema 3.0 is the current baseline. Older Community shapes, where
supported, are explicit compatibility exporters rather than shape-detected
branches in the canonical pipeline.

## Enforcement

CI must fail when:

- a protected source scan is empty;
- canonical code imports edition serializers, output projectors, or licensing;
- a projector imports a recognizer execution path;
- a writer imports `ParseResult` or plugin recognition;
- a plugin imports private extraction implementations;
- a new oversized protected module appears or a baselined hotspot grows;
- a projector changes the sealed fact fingerprint;
- a public schema breaks without an allowed compatibility decision.

## Consequences

Bundled recognizers implement the public `recognize_facts()` contract directly.
The canonical runner has no edition-envelope-to-`FactPatch` adapter. Explicit
legacy Community exporters may remain delivery compatibility surfaces, but they
are not callable from the canonical fact path. P0 completion requires both
payload-to-`ParseResult` write-back and projection methods on `ParseResult` to
remain absent.
