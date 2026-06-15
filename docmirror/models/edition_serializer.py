# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DEC → edition JSON v2.0 serializer (design 09 §4.4 / Wave 2 P1-1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

from docmirror.models.entities.domain_result import DomainExtractionResult


@dataclass
class EditionContext:
    """Presentation context for ``edition_serializer`` — not part of DEC."""

    edition: str = "community"
    detected_type: str = ""
    full_text: str = ""
    document_name: str = ""
    page_count: int = 0
    archetype: str = "key_value_document"
    domain: str = ""
    match_method: str = "plugin_fallback"
    scene_keywords: Sequence[str] = ()
    plugin_name: str = ""
    plugin_display_name: str = ""
    plugin_version: str = "community-2.0"
    support_level: str = "L2"
    parser_label: str = "docmirror-community"
    source_format: str = "pdf"
    extra_plugins: dict[str, Any] = field(default_factory=dict)
    mirror_ref: dict[str, Any] | None = None

    @classmethod
    def from_finalize(
        cls,
        parse_result: Any,
        *,
        detected_type: str,
        edition: str,
        plugin: Any | None = None,
        full_text: str = "",
    ) -> EditionContext:
        file_path = getattr(parse_result, "file_path", "") or ""
        doc_name = ""
        if file_path:
            from pathlib import Path

            doc_name = Path(file_path).name
        page_count = len(getattr(parse_result, "pages", []) or [])
        domain = detected_type
        archetype = "key_value_document"
        match_method = "plugin_fallback"
        scene_keywords: Sequence[str] = ()
        plugin_name = detected_type
        plugin_display = detected_type
        if plugin is not None:
            domain = getattr(plugin, "domain_name", detected_type) or detected_type
            plugin_name = getattr(plugin, "domain_name", detected_type) or detected_type
            plugin_display = getattr(plugin, "display_name", plugin_name) or plugin_name
            scene_keywords = getattr(plugin, "scene_keywords", ()) or ()
            if hasattr(plugin, "_detect_domain"):
                try:
                    domain = plugin._detect_domain()  # type: ignore[attr-defined]
                except Exception:
                    pass
            if getattr(plugin, "column_registry", None):
                archetype = "table_document"
                match_method = "keyword_layout_hybrid"
        if not doc_name:
            doc_name = plugin_display or detected_type
        return cls(
            edition=edition,
            detected_type=detected_type,
            full_text=full_text,
            document_name=doc_name,
            page_count=page_count,
            archetype=archetype,
            domain=domain,
            match_method=match_method,
            scene_keywords=scene_keywords,
            plugin_name=plugin_name,
            plugin_display_name=plugin_display,
            parser_label=f"docmirror-{edition}",
        )


def _quality_to_status(dec: DomainExtractionResult) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    for issue in dec.quality.issues or []:
        if issue.startswith("warning:"):
            warnings.append(issue[len("warning:") :])
        elif issue.startswith("error:"):
            errors.append(issue[len("error:") :])
        elif issue.startswith("dec_validation:"):
            warnings.append(issue)
        else:
            warnings.append(issue)
    return {
        "success": dec.quality.validation_passed and not errors,
        "warnings": warnings,
        "errors": errors,
    }


def _structured_data_block(dec: DomainExtractionResult) -> dict[str, Any]:
    sd = dec.structured_data
    if isinstance(sd, dict):
        records = sd.get("records") or []
        return {
            "fields": dict(dec.entities or {}),
            "records": records,
            "sections": sd.get("sections") or [],
            "tables": sd.get("tables") or [],
            "line_items": sd.get("line_items") or [],
            "summary": sd.get("summary")
            or {"total_rows": len(records) if isinstance(records, list) else 0},
        }
    if isinstance(sd, list):
        return {
            "fields": dict(dec.entities or {}),
            "records": sd,
            "sections": [],
            "tables": [],
            "line_items": [],
            "summary": {"total_rows": len(sd)},
        }
    return {
        "fields": dict(dec.entities or {}),
        "records": [],
        "sections": [],
        "tables": [],
        "line_items": [],
        "summary": {"total_rows": 0},
    }


def edition_serializer(dec: DomainExtractionResult, *, context: EditionContext) -> dict[str, Any]:
    """Serialize ``DomainExtractionResult`` to community/enterprise edition JSON v2.0."""
    from docmirror.plugins._base import build_classification_block

    document_type = dec.document_type or context.detected_type or "unknown"
    meta = dict(dec.metadata or {})

    classification = meta.get("classification")
    if not isinstance(classification, dict):
        classification = build_classification_block(
            document_type=document_type,
            domain=context.domain or document_type,
            archetype=context.archetype,
            match_method=context.match_method,
            text=context.full_text,
            scene_keywords=context.scene_keywords,
        )

    document = {
        "document_type": document_type,
        "document_name": context.document_name,
        "domain": context.domain or document_type,
        "archetype": context.archetype,
        "language": meta.get("language", "zh"),
        "region": meta.get("region", "CN"),
        "source_format": context.source_format,
        "page_count": context.page_count,
        "properties": dict(dec.properties or {}),
    }

    plugin_block = meta.get("plugin")
    if not isinstance(plugin_block, dict):
        plugin_block = {
            "name": context.plugin_name or document_type,
            "display_name": context.plugin_display_name or document_type,
            "version": context.plugin_version,
            "support_level": context.support_level,
        }

    metadata = {
        "generated_at": meta.get("generated_at") or datetime.now(timezone.utc).isoformat(),
        "parser": meta.get("parser") or context.parser_label,
        "parser_version": meta.get("parser_version", "2.0.0"),
        "task_id": meta.get("task_id", ""),
        "file_id": meta.get("file_id", ""),
    }
    if dec.metadata:
        metadata.update(dec.metadata)

    payload: dict[str, Any] = {
        "schema_version": "2.0",
        "edition": context.edition,
        "document": document,
        "classification": classification,
        "status": _quality_to_status(dec),
        "plugin": plugin_block,
        "data": _structured_data_block(dec),
        "plugins": {
            context.plugin_name or document_type: {
                "display_name": context.plugin_display_name or document_type,
                "edition": context.edition,
            },
            **(context.extra_plugins or {}),
        },
        "metadata": metadata,
    }

    if dec.derived_variables:
        payload["derived_variables"] = dict(dec.derived_variables)
    if context.mirror_ref:
        payload["mirror_ref"] = context.mirror_ref
    if meta.get("validation"):
        payload["validation"] = meta["validation"]
    return payload
