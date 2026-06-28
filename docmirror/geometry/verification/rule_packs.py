"""Rule pack registry for universal evidence verification."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from docmirror.geometry.verification.models import VerificationRule, VerifiedUnit
from docmirror.models.mirror.vnext import BlockInfo

RulePackBuilder = Callable[[BlockInfo, list[VerifiedUnit]], list[VerificationRule]]


@dataclass(frozen=True)
class FunctionVerificationRulePack:
    """Small adapter for registering callable verification rule packs."""

    pack_id: str
    builder: RulePackBuilder

    def build_rules(self, block: BlockInfo, units: list[VerifiedUnit]) -> list[VerificationRule]:
        return self.builder(block, units)


class VerificationRulePackRegistry:
    """Ordered registry for generic and domain-specific verification rule packs."""

    def __init__(self, packs: list[FunctionVerificationRulePack] | None = None) -> None:
        self._packs: list[FunctionVerificationRulePack] = list(packs or [])

    def register(self, pack: FunctionVerificationRulePack) -> VerificationRulePackRegistry:
        self._packs = [existing for existing in self._packs if existing.pack_id != pack.pack_id]
        self._packs.append(pack)
        return self

    def pack_ids(self) -> list[str]:
        return [pack.pack_id for pack in self._packs]

    def build_rules(self, block: BlockInfo, units: list[VerifiedUnit]) -> list[VerificationRule]:
        rules: list[VerificationRule] = []
        for pack in self._packs:
            for rule in pack.build_rules(block, units):
                rules.append(rule)
        return rules


def default_verification_rule_pack_registry() -> VerificationRulePackRegistry:
    return VerificationRulePackRegistry(
        [
            FunctionVerificationRulePack("generic_table_coverage", _table_coverage_rules),
            FunctionVerificationRulePack("generic_unit_evidence_assignment", _unit_evidence_assignment_rules),
            FunctionVerificationRulePack("statement_structure_rule_bridge", _statement_structure_rules),
        ]
    )


def _table_coverage_rules(block: BlockInfo, units: list[VerifiedUnit]) -> list[VerificationRule]:
    if block.type != "table":
        return []
    grid = block.content.get("grid") if isinstance(block.content, dict) else None
    cells = [cell for cell in (grid or {}).get("cells", []) or [] if isinstance(cell, dict)]
    if not cells:
        return []
    unit_ids = [unit.unit_id for unit in units]
    return [
        VerificationRule(
            rule_id=f"rule:{_safe_id(block.id)}:table_cell_coverage",
            rule_type="coverage",
            status="pass" if len(unit_ids) == len(cells) else "warn",
            input_unit_ids=unit_ids,
            reason="" if len(unit_ids) == len(cells) else "table_cell_unit_count_mismatch",
            score=(len(unit_ids) / len(cells)) if cells else 1.0,
        )
    ]


def _unit_evidence_assignment_rules(block: BlockInfo, units: list[VerifiedUnit]) -> list[VerificationRule]:
    applicable = [unit for unit in units if unit.status != "not_applicable"]
    if not applicable:
        return []
    missing = [
        unit.unit_id
        for unit in applicable
        if not unit.evidence_ids or not unit.page_ids or not unit.bbox
    ]
    score = (len(applicable) - len(missing)) / len(applicable)
    return [
        VerificationRule(
            rule_id=f"rule:{_safe_id(block.id)}:unit_evidence_assignment",
            rule_type="coverage",
            status="pass" if not missing else "warn",
            input_unit_ids=[unit.unit_id for unit in applicable],
            reason="" if not missing else "unit_evidence_assignment_incomplete",
            score=score,
        )
    ]


def _statement_structure_rules(block: BlockInfo, units: list[VerifiedUnit]) -> list[VerificationRule]:
    if block.type != "table":
        return []
    structure = block.content.get("statement_structure") if isinstance(block.content, dict) else None
    if not isinstance(structure, dict):
        return []
    rules: list[VerificationRule] = []
    for index, source_rule in enumerate(structure.get("rules") or [], start=1):
        if not isinstance(source_rule, dict):
            continue
        validation = source_rule.get("validation") if isinstance(source_rule.get("validation"), dict) else {}
        status = str(validation.get("status") or source_rule.get("status") or "not_evaluated")
        rules.append(
            VerificationRule(
                rule_id=f"rule:{_safe_id(block.id)}:statement_structure:{index:04d}",
                rule_type=str(source_rule.get("type") or "relationship"),
                status="pass" if status == "pass" else ("warn" if status == "warn" else "not_evaluated"),
                input_unit_ids=[unit.unit_id for unit in units],
                reason=str(validation.get("reason") or source_rule.get("reason") or ""),
                score=1.0 if status == "pass" else 0.0,
            )
        )
    return rules


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(value or "unknown")).strip("_") or "unknown"
