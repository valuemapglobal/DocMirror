# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Projection schema registry for Mirror and Edition JSON contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SCHEMAS_DIR = Path(__file__).resolve().parent.parent.parent / "configs" / "schemas"


@dataclass(frozen=True)
class ProjectionSchemaSpec:
    """Registered projection output schema."""

    name: str
    path: Path
    version: str
    description: str = ""
    compatibility: str = ""


@dataclass(frozen=True)
class ProjectionSchemaValidation:
    """Result of validating a projection payload against its schema."""

    name: str
    valid: bool
    errors: tuple[str, ...] = ()


def _builtin_specs() -> dict[str, ProjectionSchemaSpec]:
    specs = (
        ProjectionSchemaSpec(
            name="mirror",
            path=_SCHEMAS_DIR / "mirror.schema.json",
            version="1.1",
            description="Core Mirror JSON (ParseResult.to_api_dict)",
        ),
        ProjectionSchemaSpec(
            name="community",
            path=_SCHEMAS_DIR / "edition_community.schema.json",
            version="2.0",
            description="Community edition envelope (DEC v2)",
        ),
        ProjectionSchemaSpec(
            name="enterprise",
            path=_SCHEMAS_DIR / "edition_enterprise.schema.json",
            version="2.0",
            description="Enterprise edition envelope (DEC v2 + governance)",
        ),
        ProjectionSchemaSpec(
            name="finance",
            path=_SCHEMAS_DIR / "edition_finance.schema.json",
            version="3.0",
            description="Finance edition envelope (DEC v3)",
        ),
    )
    return {spec.name: spec for spec in specs}


_registry: dict[str, ProjectionSchemaSpec] = _builtin_specs()


def load_projection_registry() -> dict[str, ProjectionSchemaSpec]:
    """Return projection schema registry (built-in + registered extensions)."""
    return dict(_registry)


def get_projection_schema(name: str) -> ProjectionSchemaSpec | None:
    return load_projection_registry().get(name)


def load_projection_schema_json(name: str) -> dict[str, Any] | None:
    spec = get_projection_schema(name)
    if spec is None or not spec.path.is_file():
        return None
    with open(spec.path, encoding="utf-8") as f:
        return json.load(f)


def register_projection_schema(spec: ProjectionSchemaSpec) -> None:
    """Register a third-party or tenant-specific projection schema."""
    _registry[spec.name] = spec


def validate_projection_payload(name: str, payload: dict[str, Any]) -> ProjectionSchemaValidation:
    """Validate a projection payload against the registered JSON schema.

    Full JSON Schema validation is used when ``jsonschema`` is installed. In
    minimal environments, this still verifies that the schema exists and all
    top-level required keys are present.
    """
    schema = load_projection_schema_json(name)
    if schema is None:
        return ProjectionSchemaValidation(name=name, valid=False, errors=(f"schema not found: {name}",))
    try:
        import jsonschema

        jsonschema.validate(instance=payload, schema=schema)
        return ProjectionSchemaValidation(name=name, valid=True)
    except ImportError:
        missing = [key for key in schema.get("required", []) if key not in payload]
        return ProjectionSchemaValidation(
            name=name,
            valid=not missing,
            errors=tuple(f"missing required key: {key}" for key in missing),
        )
    except Exception as exc:
        return ProjectionSchemaValidation(name=name, valid=False, errors=(str(exc),))


__all__ = [
    "ProjectionSchemaSpec",
    "ProjectionSchemaValidation",
    "get_projection_schema",
    "load_projection_registry",
    "load_projection_schema_json",
    "register_projection_schema",
    "validate_projection_payload",
]
