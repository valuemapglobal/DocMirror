# ADR 0002: P0 canonical fact pipeline and post-seal plugin boundary

- Status: Accepted
- Date: 2026-07-23
- Supersedes: the external `DomainRecognizer -> FactPatch -> Canonical` path

## Decision

DocMirror has one mandatory parse path:

```text
CLI / REST API / Python SDK
  -> ParseRequest + ParsePolicy
  -> InputAcceptance + FCR
  -> AcceptedSource
  -> Dispatcher
  -> Adapter
  -> Canonical Pipeline
  -> SealedParseResult SSOT
```

Only after `SealedParseResult` exists may delivery execute:

```text
SealedParseResult
  -> Mirror projector
  -> unified Post-Seal PluginRegistry
  -> Community / Enterprise / Finance / scenario projectors
  -> ArtifactWriter / API response
```

The Canonical Pipeline reuses the existing MEP:

```text
Normalize -> Structure / Reconstruct -> Evidence / Classification
  -> Validation -> Seal
```

Core owns generic acceptance, extraction, evidence, structure, classification,
validation, and sealing. The seven bundled domain implementations are
substantive post-seal projectors in `docmirror/plugins/<domain>`. They are
registered through the same `PluginRegistry` used by Enterprise, Finance, and
third-party providers.

## Normative invariants

1. `AcceptedSource` binds the bytes consumed by the adapter to intake identity.
2. The Dispatcher is the only component that completes the final canonical seal.
3. Automatic classification, OCR, layout, synonyms, schemas, and generic
   canonical facts are Core-owned and independent of installed plugins.
4. There is no pre-seal plugin patch or domain-enrichment bridge.
5. `PluginProvider` contains projectors only. `DomainRecognizer`, public
   `FactPatch`, and `recognizers` are retired.
6. Plugin discovery, entitlement, selection, and execution are unreachable
   from the canonical path and occur only after a valid sealed snapshot exists.
7. A projector receives `SealedParseResult`, never mutable `ParseResult`.
8. Plugin output is derived data. It cannot change document type, canonical
   entities, evidence, datasets, sections, parse status, or another projection.
9. Plugin absence, incompatibility, lack of entitlement, timeout, and failure
    affect only that plugin artifact.
10. `ArtifactWriter` persists already-built projections and owns no recognition
    or repair behavior.

## Plugin contract

The only public execution role is:

```python
class EditionProjector(Protocol):
    domain_name: str
    edition: str

    def project(
        self,
        result: SealedParseResult,
    ) -> dict[str, Any] | None: ...
```

Providers declare supported sealed schema versions. Registration rejects an
empty provider, an old `recognizers` field, or a projector without
`domain_name`, `edition`, and callable `project()`.

A scenario needing a fact absent from the sealed model must request a Core
capability/schema change. It must not create an unofficial second fact model or
write plugin output back into Canonical.

## Enforcement

CI fails when:

- pre-seal code imports any `docmirror.plugins` module or reads `plugin.yaml`;
- public Plugin API exposes a pre-seal role;
- PluginRegistry contains recognizer or Canonical-write state;
- an output builder accepts mutable `ParseResult`;
- third-party provider code is imported before sealing;
- plugin installation or licensing changes a canonical fact fingerprint;
- a projector changes sealed integrity or another projection;
- a legacy adapter or dual execution path reappears.
