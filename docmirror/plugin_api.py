# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Stable public contracts for DocMirror extension providers.

Plugins must import contracts from this module instead of depending on private
``docmirror.plugins._runtime`` implementation modules.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pluggy import HookimplMarker
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:
    from docmirror.models.sealed import SealedParseResult

hookimpl = HookimplMarker("docmirror")
"""Public decorator for functions exposed through ``docmirror.plugins`` entry points."""


@runtime_checkable
class EditionProjector(Protocol):
    """Delivery-stage plugin role operating on an immutable snapshot."""

    @property
    def domain_name(self) -> str: ...

    @property
    def edition(self) -> str: ...

    def project(self, result: SealedParseResult) -> dict[str, Any] | None: ...


class PluginProvider(BaseModel):
    """Post-seal manifest registered by commercial and third-party providers."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")

    provider_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    api_version: str = "2"
    projectors: tuple[EditionProjector, ...] = ()
    supported_sealed_schemas: tuple[str, ...] = ("docmirror.sealed_parse_result.v1",)
    resource_package: str | None = None
    resources: dict[str, str] = Field(default_factory=dict)

    @field_validator("api_version")
    @classmethod
    def _require_projector_only_api(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if normalized != "2":
            raise ValueError("PluginProvider api_version must be '2'")
        return normalized

    @field_validator("supported_sealed_schemas")
    @classmethod
    def _require_supported_sealed_schema(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))
        if not normalized:
            raise ValueError("PluginProvider must support at least one sealed schema")
        return normalized

    @field_validator("resource_package")
    @classmethod
    def _normalize_resource_package(cls, value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("resources")
    @classmethod
    def _validate_resources(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_name, raw_path in value.items():
            name = str(raw_name or "").strip()
            path = str(raw_path or "").strip()
            relative = PurePosixPath(path)
            if not name:
                raise ValueError("plugin resource name must not be empty")
            if not path or relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"unsafe plugin resource path: {raw_path!r}")
            normalized[name] = path
        return normalized

    @model_validator(mode="after")
    def _validate_provider(self) -> PluginProvider:
        if not self.projectors:
            raise ValueError("post-seal PluginProvider requires at least one projector")
        if self.resources and not self.resource_package:
            raise ValueError("resource_package is required when resources are declared")
        return self


__all__ = [
    "EditionProjector",
    "PluginProvider",
    "hookimpl",
]
