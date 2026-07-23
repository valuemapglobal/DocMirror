# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Stable public contracts for DocMirror extension providers.

Plugins must import contracts from this module instead of depending on private
``docmirror.plugins._runtime`` implementation modules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pluggy import HookimplMarker
from pydantic import BaseModel, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    from docmirror.models.entities.parse_result import ParseResult
    from docmirror.models.sealed import SealedParseResult

hookimpl = HookimplMarker("docmirror")
"""Public decorator for functions exposed through ``docmirror.plugins`` entry points."""


class DomainPlugin(ABC):
    """Legacy combined role, kept on the public API during role separation."""

    @property
    @abstractmethod
    def domain_name(self) -> str: ...

    @property
    @abstractmethod
    def display_name(self) -> str: ...

    @property
    def provider_id(self) -> str:
        return self.domain_name

    @property
    def edition(self) -> str:
        return "community"

    @property
    def requires_license(self) -> bool:
        return False

    @property
    def scene_keywords(self) -> Sequence[str]:
        from docmirror.configs.scene.loader import get_plugin_scene_keywords

        return get_plugin_scene_keywords().get(self.domain_name, ())

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return ()

    def build_domain_data(
        self,
        _metadata: dict[str, Any],
        _entities: dict[str, Any],
    ) -> dict[str, Any] | None:
        return None

    def get_middleware_config(self) -> dict[str, Any]:
        return {}


class FactPatch(BaseModel):
    """Ephemeral, validated facts proposed by one domain recognizer.

    A patch is consumed once by the canonical pipeline. It is never retained as
    another model and deliberately cannot carry an edition envelope, artifacts,
    licensing state, or presentation data.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_id: str = Field(min_length=1)
    document_type: str | None = None
    entity_fields: dict[str, Any] = Field(default_factory=dict)
    domain_facts: dict[str, Any] = Field(default_factory=dict)
    datasets: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    sections: tuple[dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    replace_paths: frozenset[str] = frozenset()
    reason: str = "domain recognition"

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


@runtime_checkable
class DomainRecognizer(Protocol):
    """Fact-stage plugin role. Implementations must not mutate ``result``."""

    @property
    def provider_id(self) -> str: ...

    def recognize_facts(self, result: ParseResult, text: str = "") -> FactPatch: ...


@runtime_checkable
class EditionProjector(Protocol):
    """Delivery-stage plugin role operating on an immutable snapshot."""

    @property
    def edition(self) -> str: ...

    def project(self, result: SealedParseResult) -> dict[str, Any] | None: ...


class PluginProvider(BaseModel):
    """Manifest registered by built-in, commercial, and third-party providers."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    provider_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    api_version: str = "1"
    recognizers: tuple[DomainRecognizer, ...] = ()
    projectors: tuple[EditionProjector, ...] = ()


__all__ = [
    "DomainRecognizer",
    "DomainPlugin",
    "EditionProjector",
    "FactPatch",
    "PluginProvider",
    "hookimpl",
]
