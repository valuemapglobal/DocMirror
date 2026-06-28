"""Build universal verification units from reconstructed blocks."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from docmirror.geometry.verification.models import (
    VerificationCandidate,
    VerificationClaim,
    VerificationReport,
    VerifiedUnit,
)
from docmirror.geometry.verification.rule_packs import (
    VerificationRulePackRegistry,
    default_verification_rule_pack_registry,
)
from docmirror.models.mirror.vnext import BlockInfo

_MAX_SPATIAL_EVIDENCE_PER_UNIT = 32


def build_verification_report(
    *,
    blocks: list[BlockInfo],
    evidence_atoms: list[Any] | None = None,
    rule_pack_registry: VerificationRulePackRegistry | None = None,
) -> VerificationReport:
    atoms = evidence_atoms or []
    atoms_by_page = _atoms_by_page(atoms)
    atoms_by_id = _atoms_by_id(atoms)
    registry = rule_pack_registry or default_verification_rule_pack_registry()
    units: list[VerifiedUnit] = []
    claims: list[VerificationClaim] = []
    rules = []
    for block in blocks:
        block_units = _units_from_block(block)
        final_block_units: list[VerifiedUnit] = []
        for unit in block_units:
            unit = _with_spatial_evidence(unit, atoms_by_page, atoms_by_id)
            unit_claims = _claims_for_unit(unit)
            claim_ids = [claim.claim_id for claim in unit_claims]
            status, score, reasons = _unit_status(unit, unit_claims)
            final_unit = VerifiedUnit(
                **{
                    **unit.__dict__,
                    "claim_ids": claim_ids,
                    "status": status,
                    "confidence": score,
                    "reasons": reasons,
                }
            )
            units.append(final_unit)
            final_block_units.append(final_unit)
            claims.extend(unit_claims)
        rules.extend(registry.build_rules(block, final_block_units))
    return VerificationReport(units=units, claims=claims, rules=rules)


def _append_candidate(
    candidates: list[VerificationCandidate],
    candidate: VerificationCandidate,
) -> list[VerificationCandidate]:
    candidate_key = _candidate_key(candidate)
    if any(_candidate_key(existing) == candidate_key for existing in candidates):
        return list(candidates)
    return [*candidates, candidate]


def _candidate_key(candidate: VerificationCandidate) -> tuple[str, str, tuple[str, ...]]:
    return (
        candidate.source,
        str(candidate.value or "").strip(),
        tuple(candidate.evidence_ids),
    )


def _candidate_value_groups(unit: VerifiedUnit) -> list[tuple[str, VerificationCandidate]]:
    comparable: list[tuple[str, VerificationCandidate]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in unit.candidates:
        value = _normalize_candidate_value(candidate.value, unit.data_type)
        if not value:
            continue
        key = (candidate.source, value)
        if key in seen:
            continue
        seen.add(key)
        comparable.append((value, candidate))
    return comparable


def _normalize_candidate_value(value: Any, data_type: str) -> str:
    text = str(value if value is not None else "").strip()
    if not text:
        return ""
    if data_type in {"number", "amount"}:
        number = _parse_number(text)
        return f"number:{number:.12g}" if number is not None else f"invalid_number:{_compact_text(text)}"
    if data_type == "date":
        normalized = text.replace("年", "-").replace("月", "-").replace("日", "")
        normalized = normalized.replace("/", "-").replace(".", "-")
        return f"date:{_compact_text(normalized)}"
    return f"text:{_compact_text(text)}"


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", "", value.strip())


def _atoms_by_page(evidence_atoms: list[Any]) -> dict[str, list[Any]]:
    by_page: dict[str, list[Any]] = {}
    for atom in evidence_atoms:
        atom_id = _atom_id(atom)
        page_id = _atom_page_id(atom)
        if not atom_id or not page_id or not _bbox(_atom_bbox(atom)):
            continue
        by_page.setdefault(page_id, []).append(atom)
    for atoms in by_page.values():
        atoms.sort(key=lambda atom: (_bbox_sort_key(_atom_bbox(atom)), _atom_id(atom)))
    return by_page


def _atoms_by_id(evidence_atoms: list[Any]) -> dict[str, Any]:
    return {_atom_id(atom): atom for atom in evidence_atoms if _atom_id(atom)}


def _with_spatial_evidence(
    unit: VerifiedUnit,
    atoms_by_page: dict[str, list[Any]],
    atoms_by_id: dict[str, Any],
) -> VerifiedUnit:
    if unit.unit_type not in {"table_cell", "kv_field"}:
        return unit
    if not unit.page_ids or not unit.bbox or not str(unit.selected_value or "").strip():
        return unit
    if unit.evidence_ids:
        matched = [
            atoms_by_id[evidence_id]
            for evidence_id in unit.evidence_ids
            if evidence_id in atoms_by_id and _atom_text(atoms_by_id[evidence_id]).strip()
        ]
        candidate_source = "evidence_atom_text"
    else:
        matched = _spatial_evidence_for_unit(unit, atoms_by_page)
        candidate_source = "spatial_evidence_backfill"
    if not matched:
        return unit
    evidence_ids = _unique([_atom_id(atom) for atom in matched if _atom_id(atom)])
    if not evidence_ids:
        return unit
    text_fragments = [_atom_text(atom).strip() for atom in matched if _atom_text(atom).strip()]
    if text_fragments:
        candidate_value = " ".join(text_fragments[:8])
    else:
        candidate_value = f"{len(evidence_ids)} spatial evidence atom(s)"
    candidate = VerificationCandidate(
        source=candidate_source,
        value=candidate_value,
        confidence=_mean_atom_confidence(matched),
        evidence_ids=evidence_ids,
        metadata={"matched_atom_count": len(matched)},
    )
    return replace(
        unit,
        evidence_ids=_unique([*unit.evidence_ids, *evidence_ids]),
        source_refs=_unique([*unit.source_refs, candidate_source]),
        candidates=_append_candidate(unit.candidates, candidate),
    )


def _spatial_evidence_for_unit(unit: VerifiedUnit, atoms_by_page: dict[str, list[Any]]) -> list[Any]:
    bbox = _bbox(unit.bbox)
    if not bbox:
        return []
    matched: list[Any] = []
    allow_visual = unit.unit_type == "visual_object"
    for page_id in unit.page_ids:
        for atom in atoms_by_page.get(page_id, []):
            if not allow_visual and not _atom_text(atom).strip():
                continue
            atom_bbox = _bbox(_atom_bbox(atom))
            if not atom_bbox:
                continue
            if _atom_center_in_bbox(atom_bbox, bbox) or _bbox_overlap_ratio(atom_bbox, bbox) >= 0.35:
                matched.append(atom)
                if len(matched) >= _MAX_SPATIAL_EVIDENCE_PER_UNIT:
                    return matched
    return matched


def _units_from_block(block: BlockInfo) -> list[VerifiedUnit]:
    if block.type == "table":
        return _table_cell_units(block)
    if block.type == "key_value_group":
        units = _kv_units(block)
        return units or [_text_unit(block)]
    if block.type in {"artifact", "figure"} or block.role in {"seal", "signature"}:
        return [_visual_unit(block)]
    if block.text:
        return [_text_unit(block)]
    return []


def _table_cell_units(block: BlockInfo) -> list[VerifiedUnit]:
    grid = block.content.get("grid") if isinstance(block.content, dict) else None
    if not isinstance(grid, dict):
        return []
    cells = [cell for cell in grid.get("cells", []) or [] if isinstance(cell, dict)]
    units: list[VerifiedUnit] = []
    for index, cell in enumerate(cells):
        row = _int(cell.get("row_index", cell.get("row", 0)), 0)
        col = _int(cell.get("col_index", cell.get("column_index", cell.get("col", 0))), 0)
        text = _cell_value(cell)
        evidence_ids = [str(eid) for eid in cell.get("evidence_ids", []) or []]
        confidence = float(cell.get("confidence", block.confidence or 0.0) or 0.0)
        units.append(
            VerifiedUnit(
                unit_id=f"unit:{_safe_id(block.id)}:cell:{row:04d}:{col:04d}",
                unit_type="table_cell",
                block_id=block.id,
                region_ids=list(block.region_ids),
                page_ids=list(block.page_ids),
                bbox=_bbox(cell.get("bbox")) or block.bbox,
                evidence_ids=evidence_ids,
                source_refs=[str(cell.get("id") or f"cell:{index}")],
                selected_value=text,
                data_type=_infer_data_type(text),
                confidence=confidence,
                candidates=[
                    VerificationCandidate(
                        source="table_grid_cell",
                        value=text,
                        confidence=confidence,
                        evidence_ids=evidence_ids,
                    )
                ],
            )
        )
    return units


def _kv_units(block: BlockInfo) -> list[VerifiedUnit]:
    content = block.content if isinstance(block.content, dict) else {}
    raw_fields = content.get("fields") or content.get("items") or content.get("pairs")
    if isinstance(raw_fields, dict):
        fields = [{"key": key, "value": value} for key, value in raw_fields.items()]
    elif isinstance(raw_fields, list):
        fields = [field for field in raw_fields if isinstance(field, dict)]
    else:
        fields = []
    units: list[VerifiedUnit] = []
    for index, field in enumerate(fields):
        key = str(field.get("key") or field.get("name") or f"field_{index + 1}")
        value = field.get("value", field.get("text", ""))
        text = str(value if value is not None else "")
        evidence_ids = [str(eid) for eid in field.get("evidence_ids", []) or block.evidence_ids or []]
        confidence = float(field.get("confidence", block.confidence or 0.0) or 0.0)
        units.append(
            VerifiedUnit(
                unit_id=f"unit:{_safe_id(block.id)}:kv:{index:04d}",
                unit_type="kv_field",
                block_id=block.id,
                region_ids=list(block.region_ids),
                page_ids=list(block.page_ids),
                bbox=_bbox(field.get("bbox")) or block.bbox,
                evidence_ids=evidence_ids,
                source_refs=[key],
                selected_value=text,
                data_type=_infer_data_type(text),
                confidence=confidence,
                candidates=[
                    VerificationCandidate(
                        source="key_value_field",
                        value=text,
                        confidence=confidence,
                        evidence_ids=evidence_ids,
                    )
                ],
            )
        )
    return units


def _text_unit(block: BlockInfo) -> VerifiedUnit:
    text = str(block.text or "")
    evidence_ids = [str(eid) for eid in block.evidence_ids or []]
    return VerifiedUnit(
        unit_id=f"unit:{_safe_id(block.id)}:text:0000",
        unit_type="text_span",
        block_id=block.id,
        region_ids=list(block.region_ids),
        page_ids=list(block.page_ids),
        bbox=block.bbox,
        evidence_ids=evidence_ids,
        source_refs=[block.id],
        selected_value=text,
        data_type="text" if text else "unknown",
        confidence=float(block.confidence or 0.0),
        candidates=[
            VerificationCandidate(
                source="block_text",
                value=text,
                confidence=float(block.confidence or 0.0),
                evidence_ids=evidence_ids,
            )
        ],
    )


def _visual_unit(block: BlockInfo) -> VerifiedUnit:
    evidence_ids = [str(eid) for eid in block.evidence_ids or []]
    value = str(block.role or block.type or "visual_object")
    return VerifiedUnit(
        unit_id=f"unit:{_safe_id(block.id)}:visual:0000",
        unit_type="visual_object",
        block_id=block.id,
        region_ids=list(block.region_ids),
        page_ids=list(block.page_ids),
        bbox=block.bbox,
        evidence_ids=evidence_ids,
        source_refs=[block.id],
        selected_value=value,
        data_type="image",
        confidence=float(block.confidence or 0.0),
        candidates=[
            VerificationCandidate(
                source="visual_block",
                value=value,
                confidence=float(block.confidence or 0.0),
                evidence_ids=evidence_ids,
            )
        ],
    )


def _claims_for_unit(unit: VerifiedUnit) -> list[VerificationClaim]:
    return [
        _value_claim(unit),
        _candidate_vote_claim(unit),
        _assignment_claim(unit),
        _format_claim(unit),
    ]


def _value_claim(unit: VerifiedUnit) -> VerificationClaim:
    reasons: list[str] = []
    if unit.unit_type == "table_cell" and not str(unit.selected_value or "").strip() and not unit.evidence_ids:
        return VerificationClaim(
            claim_id=f"claim:{unit.unit_id}:value",
            claim_type="value_reading",
            subject_unit_id=unit.unit_id,
            status="not_applicable",
            score=1.0,
            evidence_ids=[],
            reasons=["empty_cell"],
        )
    if unit.selected_value in ("", None) and unit.unit_type != "visual_object":
        reasons.append("missing_selected_value")
    if not unit.evidence_ids:
        reasons.append("missing_evidence_refs")
    status = "verified" if not reasons else "not_evaluated"
    score = unit.confidence if status == "verified" else 0.0
    return VerificationClaim(
        claim_id=f"claim:{unit.unit_id}:value",
        claim_type="value_reading",
        subject_unit_id=unit.unit_id,
        status=status,
        score=score,
        evidence_ids=list(unit.evidence_ids),
        reasons=reasons,
    )


def _candidate_vote_claim(unit: VerifiedUnit) -> VerificationClaim:
    comparable = _candidate_value_groups(unit)
    if len(comparable) < 2:
        return VerificationClaim(
            claim_id=f"claim:{unit.unit_id}:candidate_vote",
            claim_type="candidate_vote",
            subject_unit_id=unit.unit_id,
            status="not_applicable",
            score=1.0,
            evidence_ids=list(unit.evidence_ids),
            reasons=["single_candidate"],
        )
    distinct_values = {value for value, _candidate in comparable}
    if len(distinct_values) > 1:
        return VerificationClaim(
            claim_id=f"claim:{unit.unit_id}:candidate_vote",
            claim_type="candidate_vote",
            subject_unit_id=unit.unit_id,
            status="conflict",
            score=0.0,
            evidence_ids=list(unit.evidence_ids),
            reasons=["candidate_value_conflict"],
        )
    score = sum(candidate.confidence for _value, candidate in comparable) / len(comparable)
    return VerificationClaim(
        claim_id=f"claim:{unit.unit_id}:candidate_vote",
        claim_type="candidate_vote",
        subject_unit_id=unit.unit_id,
        status="verified",
        score=score,
        evidence_ids=list(unit.evidence_ids),
    )


def _assignment_claim(unit: VerifiedUnit) -> VerificationClaim:
    reasons: list[str] = []
    if not unit.page_ids:
        reasons.append("missing_page_ref")
    if not unit.bbox:
        reasons.append("missing_bbox")
    status = "verified" if not reasons else "not_evaluated"
    return VerificationClaim(
        claim_id=f"claim:{unit.unit_id}:assignment",
        claim_type="assignment",
        subject_unit_id=unit.unit_id,
        status=status,
        score=1.0 if status == "verified" else 0.0,
        evidence_ids=list(unit.evidence_ids),
        reasons=reasons,
    )


def _format_claim(unit: VerifiedUnit) -> VerificationClaim:
    if unit.data_type not in {"number", "amount", "date"}:
        return VerificationClaim(
            claim_id=f"claim:{unit.unit_id}:format",
            claim_type="format",
            subject_unit_id=unit.unit_id,
            status="not_evaluated",
            score=1.0,
            evidence_ids=list(unit.evidence_ids),
            reasons=["no_generic_format_rule"],
        )
    if unit.data_type in {"number", "amount"} and _parse_number(str(unit.selected_value)) is None:
        return VerificationClaim(
            claim_id=f"claim:{unit.unit_id}:format",
            claim_type="format",
            subject_unit_id=unit.unit_id,
            status="conflict",
            score=0.0,
            evidence_ids=list(unit.evidence_ids),
            reasons=["numeric_format_parse_failed"],
        )
    return VerificationClaim(
        claim_id=f"claim:{unit.unit_id}:format",
        claim_type="format",
        subject_unit_id=unit.unit_id,
        status="verified",
        score=1.0,
        evidence_ids=list(unit.evidence_ids),
    )


def _unit_status(unit: VerifiedUnit, claims: list[VerificationClaim]) -> tuple[str, float, list[str]]:
    if any(claim.status == "conflict" for claim in claims):
        reasons = [reason for claim in claims for reason in claim.reasons]
        return "conflict", 0.0, reasons
    required = [claim for claim in claims if claim.claim_type in {"value_reading", "assignment"}]
    value_claim = next((claim for claim in required if claim.claim_type == "value_reading"), None)
    assignment_claim = next((claim for claim in required if claim.claim_type == "assignment"), None)
    if value_claim and value_claim.status == "not_applicable":
        if assignment_claim is None or assignment_claim.status == "verified":
            return "not_applicable", 1.0, list(value_claim.reasons)
    if required and all(claim.status == "verified" for claim in required):
        scores = [claim.score for claim in required]
        return "verified", sum(scores) / len(scores), []
    reasons = [reason for claim in required for reason in claim.reasons]
    return "not_evaluated", 0.0, reasons
def _cell_value(cell: dict[str, Any]) -> str:
    value = cell.get("value") if isinstance(cell.get("value"), dict) else {}
    selected = value.get("normalized") if value.get("normalized") is not None else cell.get("text", "")
    return str(selected if selected is not None else "")


def _infer_data_type(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown"
    if re.fullmatch(r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?", text):
        return "date"
    if _parse_number(text) is not None:
        return "amount" if any(ch in text for ch in ",，().（）") or "." in text else "number"
    return "text"


def _parse_number(value: str) -> float | None:
    cleaned = str(value or "").strip().replace(",", "").replace("，", "")
    if not cleaned or not re.search(r"\d", cleaned):
        return None
    negative = False
    if (cleaned.startswith("(") and cleaned.endswith(")")) or (cleaned.startswith("（") and cleaned.endswith("）")):
        negative = True
        cleaned = cleaned[1:-1]
    match = re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned.replace(" ", ""))
    if not match:
        return None
    number = float(match.group(0))
    return -abs(number) if negative else number


def _bbox(value: Any) -> list[float] | None:
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    try:
        x0, y0, x1, y1 = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


def _bbox_sort_key(value: Any) -> tuple[float, float, float, float]:
    bbox = _bbox(value)
    if not bbox:
        return (0.0, 0.0, 0.0, 0.0)
    return (bbox[1], bbox[0], bbox[3], bbox[2])


def _atom_center_in_bbox(atom_bbox: list[float], target_bbox: list[float]) -> bool:
    center_x = (atom_bbox[0] + atom_bbox[2]) / 2.0
    center_y = (atom_bbox[1] + atom_bbox[3]) / 2.0
    return target_bbox[0] <= center_x <= target_bbox[2] and target_bbox[1] <= center_y <= target_bbox[3]


def _bbox_overlap_ratio(atom_bbox: list[float], target_bbox: list[float]) -> float:
    left = max(atom_bbox[0], target_bbox[0])
    top = max(atom_bbox[1], target_bbox[1])
    right = min(atom_bbox[2], target_bbox[2])
    bottom = min(atom_bbox[3], target_bbox[3])
    if right <= left or bottom <= top:
        return 0.0
    atom_area = max((atom_bbox[2] - atom_bbox[0]) * (atom_bbox[3] - atom_bbox[1]), 1e-6)
    return ((right - left) * (bottom - top)) / atom_area


def _atom_id(atom: Any) -> str:
    return str(_field(atom, "id") or "")


def _atom_page_id(atom: Any) -> str:
    return str(_field(atom, "page_id") or "")


def _atom_bbox(atom: Any) -> Any:
    return _field(atom, "bbox")


def _atom_text(atom: Any) -> str:
    return str(_field(atom, "text") or "")


def _atom_confidence(atom: Any) -> float:
    try:
        return float(_field(atom, "confidence") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _mean_atom_confidence(atoms: list[Any]) -> float:
    if not atoms:
        return 0.0
    return sum(_atom_confidence(atom) for atom in atoms) / len(atoms)


def _field(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(value or "unknown")).strip("_") or "unknown"


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
