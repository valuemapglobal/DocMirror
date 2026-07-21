"""Stable public types for the self-contained Community Bundle JSON API."""

from __future__ import annotations

from typing import Any, TypedDict


class CommunitySchema(TypedDict):
    name: str
    version: str
    edition: str
    domain: str
    support_level: str


class CommunityRecordRequired(TypedDict):
    record_id: str
    normalized: dict[str, Any]
    canonical_raw: dict[str, Any]
    raw: dict[str, Any]
    source: dict[str, Any]


class CommunityRecord(CommunityRecordRequired, total=False):
    confidence: float | str
    review: dict[str, Any]


class CommunityCompleteness(TypedDict):
    expected_row_count: int
    emitted_row_count: int
    omitted_row_count: int
    verified: bool
    basis: str


class CommunityColumnRequired(TypedDict):
    key: str
    label: str
    type: str
    nullable: bool
    raw_available: bool
    evidence_available: bool


class CommunityColumn(CommunityColumnRequired, total=False):
    unit: str


class CommunityDataset(TypedDict):
    id: str
    name: str
    label: str
    type: str
    section_id: str
    csv: str
    row_count: int
    grain: str
    primary_key: str
    schema_version: str
    status: str
    columns: list[CommunityColumn]
    completeness: CommunityCompleteness
    rows: list[CommunityRecord]


class CommunityBundle(TypedDict):
    schema: CommunitySchema
    document: dict[str, Any]
    sections: list[dict[str, Any]]
    datasets: list[CommunityDataset]
    files: dict[str, str]
    warnings: list[dict[str, Any]]


__all__ = [
    "CommunityBundle",
    "CommunityColumn",
    "CommunityCompleteness",
    "CommunityDataset",
    "CommunityRecord",
    "CommunitySchema",
]
