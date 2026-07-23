# ADR 0004: P2 plugin resource ownership

- Status: Accepted
- Date: 2026-07-22
- Depends on: ADR 0003

## Decision

P2 does not add a runtime node, execution mode, fact store, plugin API version,
or Python architecture module. The runtime defined by ADR 0002 remains
normative. Existing `DomainPlugin`, `PluginProvider`, `PluginRegistry`, entry
point discovery, extension points, and `FactPatch` remain the implementation
mechanisms.

P2 moves production business knowledge out of generic Core packages and into
the existing domain-plugin directories. Each existing plugin may add one
declarative `plugin.yaml` and package-local non-Python resources. The manifest
is an inventory and discovery input; it does not execute recognition or produce
facts.

The owner authorized implementation and replaced calendar/release-cycle waits
with qualification against the current candidate's reproducible technical
evidence. Passing the migration script alone is not evidence that all shared
runtime business semantics have a plugin owner.

## Runtime invariant

```text
AcceptedSource + ParsePolicy -> Dispatcher -> Adapter -> Canonical Assembly
  -> generic Normalize / Structure / Entity
  -> existing DomainRecognizer -> FactPatch
  -> Canonical Validation + Mutation Audit
  -> seal() -> SealedParseResult
  -> sibling Mirror / Community / Enterprise / Finance projectors
  -> ArtifactWriter
```

Plugin manifests, resource discovery, and migration gates are not runtime
facts and are not additional nodes in this chain.

## Resource-manifest convention

The accepted package-local form is:

```text
docmirror/plugins/<domain>/
  community_plugin.py
  plugin.yaml
  resources/
    classification.yaml
    field_mappings.yaml
    institutions.yaml
    table_styles.yaml
    dataset_contract.yaml
    ocr_corrections.yaml
```

Only resources used by a domain are present. Existing Python files remain in
place; the convention does not require new recognizer, context, provider, or
loader classes.

The minimal manifest is:

```yaml
schema_version: 1
provider:
  id: bank_statement
  domain_name: bank_statement
  edition: community
  version: community-1
  implementation: docmirror.plugins.bank_statement.community_plugin:plugin
classification:
  aliases: [bank_reconciliation]
  resource: resources/classification.yaml
resources:
  field_mappings: resources/field_mappings.yaml
  institutions: resources/institutions.yaml
  table_styles: resources/table_styles.yaml
  dataset_contract: resources/dataset_contract.yaml
fact_outputs:
  document_type: bank_statement
  datasets: [transactions]
```

All paths are relative package resources and must be readable from an installed
wheel through `importlib.resources`. A manifest must not contain executable
business expressions. One asset has one source of truth; permanent dual reads
from Core and plugin resources are forbidden.

## Production business assets to migrate

| Current source | Plugin owner or destination |
| --- | --- |
| `configs/yaml/bank_statement/*` | `plugins/bank_statement/resources/` |
| bank entries in `institution_registry.yaml` | `plugins/bank_statement/resources/institutions.yaml` |
| six owned sections of `scene_keywords.yaml` | corresponding domain plugin |
| all remaining fallback scenes | `plugins/generic/resources/classification.yaml` |
| owned sections of `key_synonyms.yaml` | corresponding domain plugin |
| owned sections of `document_field_schemas.yaml` | corresponding domain plugin or generic fallback |
| business sections of `layout_profiles.yaml` | corresponding plugin table/style resources |
| business OCR correction packs | corresponding plugin resources |
| `domain_contracts/community_core.yaml` | per-plugin dataset contracts |
| `plugin_capability.yaml` | derived from discovered plugin manifests |

Architecture, stability, release evidence, test fixture catalogs, public
projection schemas, format capabilities, privacy, failure codes, and generic
runtime/performance configuration remain centrally governed. Their references
to a domain for testing or release evidence do not make them runtime business
logic.

## Core cleanup targets

Migration removes concrete-domain decisions from existing Core files without
replacing them with a new abstraction layer. The main targets are:

- domain-specific evidence rules in `layout/scene/evidence_engine.py`;
- bank vocabulary in `layout/vocabulary.py`;
- `BANK_STATEMENT` defaults in table pipeline stages;
- domain classification in `input/extraction/scanned_table_reconstructor.py`;
- bank-only institution middleware;
- VAT, payment, bank, and credit-report branches in models and projectors;
- direct credit-report imports in plugin runtime extension registration.

Core keeps generic text, OCR, geometry, physical tables, evidence, structural
heuristics, canonical validation, mutation audit, sealing, and generic
projection. Existing plugin recognizers interpret the generic evidence and
continue to return the existing `FactPatch` model.

## Migration order

1. Add manifest reading to the existing `PluginRegistry`; do not create another
   registry or loader subsystem.
2. Migrate `bank_statement` as the complete vertical reference.
3. Migrate WeChat and Alipay resources and remove payment projector branches.
4. Migrate VAT and business-license field/OCR resources.
5. Migrate credit-report resources and remove direct Core/runtime imports.
6. Move remaining fallback classification and field resources to `generic`.
7. Delete central production business assets and hard-coded built-in lists.
8. Prove that a new domain changes only its plugin package, tests, and docs.

Every resource move is atomic: add the plugin resource, change its existing
consumer, delete the central entry, and run Golden/fingerprint verification in
one change. A fallback to the former Core business resource is not permitted.

## Entry and exit gates

P2 exits only when:

- adding a business domain produces no Core diff;
- Core contains no concrete-domain algorithm selection;
- production institution templates, field maps, classification dictionaries,
  table styles, business validation, and dataset contracts have plugin owners;
- a plugin wheel contains its declared resources;
- projectors and `ArtifactWriter` require no change for a new domain;
- missing, failed, unauthorized, or timed-out plugins cannot alter generic Core
  facts;
- worker-count fact determinism and the P1 stability gates remain green.

## Current gate state

The 1.0.12 candidate satisfies the current-candidate technical gates defined by
ADR 0003. Any future core-contract fingerprint change invalidates that evidence
and requires a new qualification run.
