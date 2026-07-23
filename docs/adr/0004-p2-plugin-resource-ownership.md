# ADR 0004: P2 canonical resource ownership and post-seal plugins

- Status: Accepted
- Date: 2026-07-23
- Depends on: ADR 0003

## Decision

The seven existing domain implementations and resources remain physically in:

```text
docmirror/plugins/<domain>/
  community_plugin.py
  plugin.yaml
  resources/
```

Their location is retained to minimize migration risk and keep wheel packaging
stable. Their architectural ownership is Core:

- loaded only from the fixed `CANONICAL_DOMAIN_IDS` inventory;
- consumed by Core configuration and `CanonicalDomainEnricher`;
- versioned and qualified with Core;
- never discovered through entry points;
- never registered in `PluginRegistry`;
- never affected by plugin enablement, installation, or licensing.

This is a deliberate physical-colocation exception, not a runtime exception.

## Runtime boundary

```text
Canonical resources + fixed capabilities
  -> Canonical Pipeline
  -> SealedParseResult
  -> PluginProvider + PluginRegistry
  -> EditionProjector
  -> derived artifact
```

There is no line from PluginProvider, PluginRegistry, or external resources
back to classification, OCR, layout, schema validation, Canonical enrichment,
or `ParseResult`.

## Resource ownership

Core-owned resources include:

- classification rules and scene keywords;
- OCR correction packs and layout profiles;
- field schemas, key synonyms, institutions, and table semantics;
- domain contracts and canonical dataset definitions.

Post-seal plugin resources may include:

- output templates and report layouts;
- edition-specific mapping and validation rules;
- presentation dictionaries;
- plugin-local export configuration.

External providers cannot declare a resource that Core enumerates. Core reads
its fixed domain resource inventory directly; PluginRegistry reads only
resources belonging to discovered projector providers after the seal boundary.

## Extension rule

A normal business extension implements `EditionProjector` and changes no Core
file. A new requirement that changes classification, canonical document type,
facts, evidence, or sealed schema is a Core capability proposal and follows the
Core Hardening route.

No compatibility adapter exists for `DomainRecognizer`, `FactPatch`, or
recognizer-bearing providers.

## Exit gates

P2 exits only when:

- Canonical code has no dependency on `docmirror.plugins._runtime`;
- PluginRegistry contains projectors only;
- third-party modules remain unloaded until a sealed result requests output;
- malformed recognizer-bearing providers are rejected;
- plugin resources are invisible to Core;
- all seven Canonical fingerprints remain stable;
- external projector E2E and chaos tests pass;
- the complete P0/P1/P2 architecture validation suite is green.
