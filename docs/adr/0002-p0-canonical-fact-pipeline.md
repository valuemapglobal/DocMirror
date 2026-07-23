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
  -> Mirror / Community projectors
  -> lazy PluginProvider discovery + PluginRegistry selection
  -> Enterprise / Finance / scenario projectors
  -> ArtifactWriter / API response
```

The Canonical Pipeline reuses the existing MEP:

```text
Normalize -> Structure / Reconstruct -> Evidence / Classification
  -> CanonicalDomainEnricher -> Validation -> Seal
```

`CanonicalDomainEnricher` selects one of seven fixed, Core-shipped
capabilities: generic, bank statement, WeChat payment, Alipay payment, VAT
invoice, business license, and credit report. Their Python and resource files
remain physically colocated under `docmirror/plugins/<domain>` for packaging
stability, but they are Core code: they are loaded from a closed inventory,
never registered as `PluginProvider`, and cannot be supplied or replaced by an
external package.

## Normative invariants

1. `AcceptedSource` binds the bytes consumed by the adapter to intake identity.
2. The Dispatcher is the only component that completes the final canonical seal.
3. Automatic classification, OCR, layout, synonyms, schemas, and canonical
   domain enrichment are Core-owned and independent of installed plugins.
4. `CanonicalPatch` is a private transactional Core mechanism. It is not part
   of `docmirror.plugin_api`.
5. Existing non-empty facts win unless a Core patch declares an evidence-bound
   replacement. Every applied change is audited.
6. `PluginProvider` contains projectors only. `DomainRecognizer`, public
   `FactPatch`, and `recognizers` are retired.
7. Plugin discovery, entitlement, selection, and execution are unreachable
   from the canonical path and occur only after a valid sealed snapshot exists.
8. A projector receives `SealedParseResult`, never mutable `ParseResult`.
9. Plugin output is derived data. It cannot change document type, canonical
   entities, evidence, datasets, sections, parse status, or another projection.
10. Plugin absence, incompatibility, lack of entitlement, timeout, and failure
    affect only that plugin artifact.
11. `ArtifactWriter` persists already-built projections and owns no recognition
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

- canonical code imports `docmirror.plugins._runtime`;
- public Plugin API exposes a pre-seal role;
- PluginRegistry contains recognizer state or scans bundled canonical manifests;
- an output builder accepts mutable `ParseResult`;
- third-party provider code is imported before sealing;
- plugin installation or licensing changes a canonical fact fingerprint;
- a projector changes sealed integrity or another projection;
- a legacy adapter or dual execution path reappears.
