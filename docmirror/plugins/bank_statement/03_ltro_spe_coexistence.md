# ADR-M13-04 — LTRO Coexistence with SSO/SPE

**Status:** Adopted
**Related:** [Mirror Layer Design](../../../docs/design/13_mirror_layer_first_principles_redesign.md) · ADR-BS-04

## Decision

The bank statement Plugin retains the **Logical Table Reconstruction Orchestrator (LTRO)**, running in parallel with the Mirror **SSO/SPE** for auditing purposes. They do not replace each other.

## Routing Order

1. Mirror has produced a physical table → `reconstruction_source=mirror_table` (preferred).
2. Mirror `tables=[]` and SPE indicates pipe ledger (`should_force_ltro`) → LTRO `pipe_text`.
3. SPE explicitly states `section_led` + `route_section_dominant` and `H_pipe_grid` is below the veto threshold → **block** pipe LTRO (`should_block_pipe_ltro`).
4. Otherwise → `spaced_ocr` or `none`.

## Audit Fields

- Mirror: `parser_info.structure` (SPE)
- Plugin: `ReconstructionMeta.spe_primary` / `spe_table_extraction` / `reconstruction_source`
- Cross-warning: `spe_ltro_warnings()` (e.g. `spe:mismatch_section_route_with_pipe_grid`)

## Implementation Entry Points

| Module | Responsibility |
|--------|---------------|
| `core/analyze/spe_consumer.py` | SPE reading and LTRO gating |
| `plugins/bank_statement/ltro.py` | LTRO strategy chain |
| `plugins/bank_statement/context.py` | Inject SPE into StyleContext |
