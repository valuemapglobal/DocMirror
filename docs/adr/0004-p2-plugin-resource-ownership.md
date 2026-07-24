# ADR 0004: P2 canonical resource ownership and post-seal plugins

- Status: Accepted
- Date: 2026-07-23
- Depends on: ADR 0003

## Decision

The seven domain projector implementations remain physically in:

```text
docmirror/plugins/<domain>/
  community_plugin.py
  plugin.yaml
  resources/
```

They are post-seal plugins, not Core code. Each can derive domain facts from a
sealed read view, validate them, and assemble its edition JSON. Bundled
Community providers and external Enterprise/Finance providers share one
`PluginRegistry`.

## Runtime boundary

```text
Core routing/classification resources
  -> Canonical Pipeline
  -> SealedParseResult
  -> unified Post-Seal PluginRegistry
  -> Community / Enterprise / Finance EditionProjector
  -> derived artifact
```

There is no line from PluginProvider, PluginRegistry, or external resources
back to classification, OCR, layout, schema validation, Canonical enrichment,
or `ParseResult`.

## Resource ownership

Core-owned pre-seal resources under `docmirror/configs/domain` include:

- classification rules and scene keywords;
- OCR correction packs and layout profiles;
- key synonyms and generic domain contracts needed by the Canonical Pipeline.

Post-seal plugin resources include:

- output templates and report layouts;
- edition-specific mapping and validation rules;
- presentation dictionaries;
- plugin-local export configuration.
- business field schemas, institution dictionaries, table styles, and
  edition-specific confidence policies.

`plugin.yaml` is a post-seal projection manifest only. It may declare provider
identity, projection behavior, projection outputs, and plugin-local resources;
it must not contain Core `routing`, `classification`, `capabilities`, or
`dec_validation` sections.

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

- pre-seal code has no dependency on any `docmirror.plugins` module;
- PluginRegistry contains projectors only;
- third-party modules remain unloaded until a sealed result requests output;
- malformed recognizer-bearing providers are rejected;
- plugin resources are invisible to Core;
- all seven Canonical fingerprints remain stable;
- external projector E2E and chaos tests pass;
- the complete P0/P1/P2 architecture validation suite is green.
