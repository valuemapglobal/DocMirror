# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate and transactionally apply Core-owned canonical fact patches."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from docmirror.models.entities.parse_result import DocumentSection, ParseResult


class CanonicalPatch(BaseModel):
    """Ephemeral facts proposed by one fixed Core canonical capability."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    capability_id: str = Field(min_length=1)
    document_type: str | None = None
    entity_fields: dict[str, Any] = Field(default_factory=dict)
    domain_facts: dict[str, Any] = Field(default_factory=dict)
    datasets: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    sections: tuple[dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    replace_paths: frozenset[str] = frozenset()
    reason: str = "canonical recognition"

    @field_validator("document_type")
    @classmethod
    def _normalize_document_type(cls, value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("datasets")
    @classmethod
    def _validate_dataset_records(
        cls,
        value: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        for dataset_id, rows in value.items():
            if not str(dataset_id).strip():
                raise ValueError("dataset id must not be empty")
            record_ids: set[str] = set()
            for row in rows:
                record_id = str(row.get("record_id") or "")
                if not record_id:
                    raise ValueError(f"dataset {dataset_id!r} contains a row without record_id")
                if record_id in record_ids:
                    raise ValueError(f"dataset {dataset_id!r} contains duplicate record_id {record_id!r}")
                record_ids.add(record_id)
        return value


_ENTITY_FIELDS = frozenset(
    {
        "subject_name",
        "subject_id",
        "organization",
        "document_date",
        "period_start",
        "period_end",
    }
)


def validate_canonical_patch(patch: CanonicalPatch) -> CanonicalPatch:
    """Re-validate at the canonical trust boundary and reject output concerns."""
    validated = CanonicalPatch.model_validate(patch.model_dump(mode="python"))
    forbidden = {"edition", "schema_version", "artifact", "license", "licensing", "markdown"}
    leaked = forbidden & set(validated.domain_facts)
    if leaked:
        raise ValueError(f"CanonicalPatch contains delivery-only keys: {sorted(leaked)}")
    unknown_entity_fields = set(validated.entity_fields) - _ENTITY_FIELDS
    if unknown_entity_fields:
        raise ValueError(f"CanonicalPatch contains unsupported entity fields: {sorted(unknown_entity_fields)}")

    declared_paths: set[str] = set()
    if validated.document_type:
        declared_paths.add("entities.document_type")
    declared_paths.update(f"entities.{key}" for key in validated.entity_fields)
    declared_paths.update(f"entities.domain_specific.{key}" for key in validated.domain_facts)
    declared_paths.update(f"entities.domain_specific.{key}" for key in validated.datasets)
    if validated.sections:
        declared_paths.add("sections")
    undeclared_replacements = set(validated.replace_paths) - declared_paths
    if undeclared_replacements:
        raise ValueError(
            f"CanonicalPatch replace_paths do not correspond to proposed facts: {sorted(undeclared_replacements)}"
        )
    if validated.replace_paths:
        if not validated.evidence_ids:
            raise ValueError("CanonicalPatch replacement requires evidence_ids")
        if validated.reason.strip() == "canonical recognition":
            raise ValueError("CanonicalPatch replacement requires an explicit reason")
    return validated


def _canonical_evidence_ids(result: ParseResult) -> set[str]:
    """Collect evidence identifiers that a replacement may cite."""
    identifiers: set[str] = set()
    plane = result.evidence_plane
    if plane is not None:
        for page in plane.pages:
            identifiers.update(str(value) for value in page.evidence_ids if value)
        store = plane.evidence
        for collection_name in ("text_atoms", "visual_atoms", "image_atoms", "vector_atoms"):
            for atom in getattr(store, collection_name, ()):
                if getattr(atom, "id", ""):
                    identifiers.add(str(atom.id))
    for page in result.pages:
        identifiers.update(str(value) for value in getattr(page, "evidence_ids", ()) if value)
        for block in (*page.texts, *page.key_values, *page.tables):
            identifiers.update(str(value) for value in getattr(block, "evidence_ids", ()) if value)
        for table in page.tables:
            for row in table.rows:
                identifiers.update(str(value) for value in getattr(row, "evidence_ids", ()) if value)
                for cell in row.cells:
                    identifiers.update(str(value) for value in getattr(cell, "evidence_ids", ()) if value)
    return identifiers


def _replace_allowed(patch: CanonicalPatch, path: str) -> bool:
    return path in patch.replace_paths


def _record_change(
    result: ParseResult,
    patch: CanonicalPatch,
    *,
    path: str,
    old_value: Any,
    new_value: Any,
) -> None:
    result.record_mutation(
        middleware_name=f"canonical:{patch.capability_id}",
        target_block_id="parse_result",
        field_changed=path,
        old_value=old_value,
        new_value=new_value,
        confidence=patch.confidence,
        reason=patch.reason,
    )


def _apply_entity_field(result: ParseResult, patch: CanonicalPatch, key: str, value: Any) -> None:
    if key not in _ENTITY_FIELDS or value in (None, ""):
        return
    path = f"entities.{key}"
    old_value = getattr(result.entities, key, None)
    if old_value not in (None, "") and not _replace_allowed(patch, path):
        return
    if old_value != value:
        setattr(result.entities, key, str(value))
        _record_change(result, patch, path=path, old_value=old_value, new_value=str(value))


def _coerce_sections(raw_sections: tuple[dict[str, Any], ...]) -> list[DocumentSection]:
    sections: list[DocumentSection] = []
    for index, raw in enumerate(raw_sections, start=1):
        item = dict(raw)
        start = max(
            1,
            int(
                item.pop("source_page_start", None)
                or item.pop("logical_page_start", None)
                or item.get("page_start")
                or 1
            ),
        )
        end = max(
            start,
            int(
                item.pop("source_page_end", None) or item.pop("logical_page_end", None) or item.get("page_end") or start
            ),
        )
        item["id"] = str(item.get("id") or f"section_{index}")
        item["title"] = str(item.get("title") or item.get("name") or f"章节 {index}")
        item["name"] = str(item.get("name") or item["title"])
        item["page_start"] = start
        item["page_end"] = end
        sections.append(DocumentSection.model_validate(item))
    return sections


def _apply_canonical_patch_in_place(result: ParseResult, patch: CanonicalPatch) -> None:
    """Apply a validated patch to an isolated candidate result."""
    patch = validate_canonical_patch(patch)

    if patch.document_type:
        path = "entities.document_type"
        old_type = str(result.entities.document_type or "")
        if old_type in {"", "unknown", "generic"} or _replace_allowed(patch, path):
            if old_type != patch.document_type:
                result.entities.document_type = patch.document_type
                _record_change(result, patch, path=path, old_value=old_type, new_value=patch.document_type)

    for key, value in patch.entity_fields.items():
        _apply_entity_field(result, patch, str(key), value)

    extension = dict(result.entities.domain_specific or {})
    for key, value in patch.domain_facts.items():
        path = f"entities.domain_specific.{key}"
        old_value = extension.get(key)
        if key in extension and old_value not in (None, "") and not _replace_allowed(patch, path):
            continue
        if old_value != value:
            extension[key] = value
            _record_change(result, patch, path=path, old_value=old_value, new_value=value)

    for dataset_id, rows in patch.datasets.items():
        path = f"entities.domain_specific.{dataset_id}"
        old_value = extension.get(dataset_id)
        if dataset_id in extension and old_value not in (None, []) and not _replace_allowed(patch, path):
            continue
        new_value = [dict(row) for row in rows]
        if old_value != new_value:
            extension[dataset_id] = new_value
            _record_change(result, patch, path=path, old_value=old_value, new_value=new_value)
    result.entities.domain_specific = extension

    if patch.sections:
        path = "sections"
        old_sections = [item.model_dump(mode="json") for item in result.sections]
        if not result.sections or _replace_allowed(patch, path):
            new_sections = _coerce_sections(patch.sections)
            new_dump = [item.model_dump(mode="json") for item in new_sections]
            if old_sections != new_dump:
                result.sections = new_sections
                _record_change(result, patch, path=path, old_value=old_sections, new_value=new_dump)

    for warning in patch.warnings:
        if warning and warning not in result.parser_info.warnings:
            result.parser_info.warnings.append(warning)
            _record_change(
                result,
                patch,
                path="parser_info.warnings",
                old_value=None,
                new_value=warning,
            )


def apply_canonical_patch(result: ParseResult, patch: CanonicalPatch) -> ParseResult:
    """Transactionally apply one patch and return a validated replacement.

    The caller-owned result is never modified. All field, dataset, and section
    changes are first applied to an isolated candidate. If any later operation
    fails, the candidate is discarded and the original remains byte-for-byte
    unchanged.
    """
    if not isinstance(result, ParseResult):
        raise TypeError(f"apply_canonical_patch expects ParseResult; got {type(result).__name__}")
    validated_patch = validate_canonical_patch(patch)
    if validated_patch.replace_paths:
        available_evidence = _canonical_evidence_ids(result)
        missing_evidence = set(validated_patch.evidence_ids) - available_evidence
        if missing_evidence:
            raise ValueError(f"CanonicalPatch replacement cites unknown evidence_ids: {sorted(missing_evidence)}")
    candidate = result.model_copy(deep=True)
    _apply_canonical_patch_in_place(candidate, validated_patch)
    return ParseResult.model_validate(candidate.model_dump(mode="python", exclude_none=False))


__all__ = ["CanonicalPatch", "apply_canonical_patch", "validate_canonical_patch"]
