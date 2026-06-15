# ADR-M13-04 — LTRO 与 SSO/SPE 共存

**状态：** 已采纳  
**关联：** [Mirror 层方案](../../../docs/design/13_mirror_layer_first_principles_redesign.md) · ADR-BS-04

## 决策

银行流水 Plugin 保留 **Logical Table Reconstruction Orchestrator (LTRO)**，与 Mirror **SSO/SPE** 并行审计，不互相替代。

## 路由顺序

1. Mirror 若已产出物理表 → `reconstruction_source=mirror_table`（优先）。
2. Mirror `tables=[]` 且 SPE 指示 pipe ledger（`should_force_ltro`）→ LTRO `pipe_text`。
3. SPE 明确 `section_led` + `route_section_dominant` 且 `H_pipe_grid` 低于 veto 阈值 → **禁止** pipe LTRO（`should_block_pipe_ltro`）。
4. 其余 → `spaced_ocr` 或 `none`。

## 审计字段

- Mirror：`parser_info.structure`（SPE）
- Plugin：`ReconstructionMeta.spe_primary` / `spe_table_extraction` / `reconstruction_source`
- 交叉告警：`spe_ltro_warnings()`（如 `spe:mismatch_section_route_with_pipe_grid`）

## 实现入口

| 模块 | 职责 |
|------|------|
| `core/analyze/spe_consumer.py` | SPE 读取与 LTRO 门控 |
| `plugins/bank_statement/ltro.py` | LTRO 策略链 |
| `plugins/bank_statement/context.py` | 注入 SPE 到 StyleContext |
