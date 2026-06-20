# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Plugin Execution Contract (PEC) — unified plugin runner after Mirror extraction.

Orchestrates community, enterprise, and finance edition extract in one code path:
match plugin by ``document_type``, run ``extract_from_mirror`` / ``extract`` /
``build_domain_data``, normalize through DEC validation, serialize edition JSON,
then invoke post-extract hooks (edition enrichment only; Core Mirror is not mutated).
Does **not** mutate ``ParseResult`` during extract.

Pipeline role: called after Core ``ParseResult`` is ready; ``build_all_projections``
snapshots Mirror JSON before invoking this runner.

Key exports: ``run_plugin_extract``, ``run_plugin_extract_sync``.

Dependencies: ``community`` (discovery), ``post_extract.runner`` (hooks),
``licensing.entitlements`` / ``licensing.lifecycle`` (edition gating),
``models.edition_serializer``, ``models.entities.domain_result``.
"""

from __future__ import annotations

import asyncio
import copy
import importlib
import inspect
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from docmirror.models.entities.parse_result import ParseResult
from docmirror.plugins._base import build_classification_block
from docmirror.plugins.community import (
    find_premium_community_plugin,
    get_generic_community_plugin,
    is_community_generic_enabled,
    normalize_premium_document_type,
    should_mirror_only,
)
from docmirror.plugins.post_extract.runner import run_post_extract_hooks

logger = logging.getLogger(__name__)

Edition = Literal["community", "enterprise", "finance"]

_GENERIC_TYPES = frozenset({"", "unknown", "generic"})
_LICENSE_WARNING = "_license_warning"
_MIRROR_ONLY_WARNING = "mirror_only:no_community_plugin"


def _plugin_document_type(result: ParseResult, detected_type: str) -> str:
    """Resolve PEC plugin domain (M9: MEP hint or alias map)."""
    ds = getattr(result.entities, "domain_specific", None)
    if isinstance(ds, dict):
        hinted = ds.get("plugin_document_type")
        if hinted:
            return str(hinted)
    mapped = normalize_premium_document_type(detected_type)
    if mapped not in _GENERIC_TYPES:
        return mapped
    if isinstance(ds, dict):
        scene = ds.get("extractor_scene_hint") or ds.get("pre_analyzer_scene_hint")
        confidence = float(ds.get("extractor_scene_confidence") or 0.0)
        if scene and confidence >= 0.70:
            from_scene = normalize_premium_document_type(str(scene))
            if from_scene not in _GENERIC_TYPES:
                return from_scene
    return mapped


def _premium_feature_name(domain_name: str) -> str:
    from docmirror.plugins.licensing.contract import premium_feature

    return premium_feature(domain_name)


def _is_edition_plugin_licensed(plugin: Any) -> bool:
    """
    Check enterprise/finance license for plugins with ``requires_license=True``.

    Delegates to ``licensing.entitlements.is_entitled`` (SSOT).
    """
    if not getattr(plugin, "requires_license", False):
        return True

    from docmirror.plugins.licensing.entitlements import is_entitled

    return is_entitled(getattr(plugin, "domain_name", "") or "")


def _wrap_license_degraded(
    community_payload: dict[str, Any],
    *,
    edition: Edition,
    plugin: Any,
) -> dict[str, Any]:
    """Community baseline for an edition output file with license degradation markers."""
    from docmirror.plugins.composition import apply_license_degrade

    return apply_license_degrade(community_payload, edition=edition, plugin=plugin)


def _finalize_extract(
    result: ParseResult,
    extracted: dict[str, Any],
    *,
    edition: Edition,
    detected_type: str,
    plugin: Any | None = None,
) -> dict[str, Any]:
    from docmirror.models.edition_serializer import EditionContext, edition_serializer
    from docmirror.models.entities.domain_result import (
        _is_edition_envelope_passthrough,
        normalize_domain_result,
    )
    from docmirror.models.schemas.loader import validate_dec

    dec = normalize_domain_result(extracted)
    if not dec.document_type or dec.document_type == "unknown":
        dec.document_type = detected_type
    issues = validate_dec(dec)
    if issues:
        dec.quality.issues.extend([f"dec_validation:{i}" for i in issues[:5]])

    if _is_edition_envelope_passthrough(extracted):
        out = extracted
        if issues:
            warnings = out.setdefault("status", {}).setdefault("warnings", [])
            for item in issues[:5]:
                tag = f"dec_validation:{item}"
                if tag not in warnings:
                    warnings.append(tag)
    else:
        ctx = EditionContext.from_finalize(
            result,
            detected_type=detected_type,
            edition=edition,
            plugin=plugin,
        )
        out = edition_serializer(dec, context=ctx)

    run_post_extract_hooks(
        result,
        extracted=out,
        edition=edition,
        document_type=detected_type,
        plugin=plugin,
    )
    return out


def _mirror_only_payload(
    result: ParseResult,
    detected_type: str,
    edition: Edition,
) -> dict[str, Any]:
    """Honest empty-state envelope when Mirror is complete but no community plugin exists."""
    file_path = getattr(result, "file_path", "")
    doc_name = Path(file_path).name if file_path else detected_type
    return {
        "schema_version": "2.0",
        "edition": edition,
        "document": {
            "document_type": detected_type,
            "document_name": doc_name,
            "domain": detected_type,
            "archetype": "mirror_only",
            "language": "zh",
            "region": "CN",
            "source_format": "pdf",
            "page_count": len(getattr(result, "pages", [])),
            "properties": {},
        },
        "classification": build_classification_block(
            document_type=detected_type,
            domain=detected_type,
            archetype="mirror_only",
            match_method="capability_matrix",
            text="",
            scene_keywords=(),
        ),
        "status": {
            "success": True,
            "warnings": [_MIRROR_ONLY_WARNING],
            "errors": [],
        },
        "plugin": {
            "name": detected_type,
            "display_name": detected_type,
            "version": f"{edition}-mirror-only",
            "support_level": "L0",
        },
        "data": {
            "fields": {},
            "records": [],
            "sections": [],
            "tables": [],
            "line_items": [],
            "summary": {"total_rows": 0},
        },
        "mirror_ref": {
            "document_type": detected_type,
            "table_count": result.total_tables,
            "page_count": result.page_count,
        },
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "parser": f"docmirror-{edition}",
            "parser_version": "2.0.0",
            "task_id": "",
            "file_id": "",
        },
    }


def _edition_package_available(edition: str) -> bool:
    if edition == "community":
        return True
    if edition == "enterprise":
        try:
            importlib.import_module("docmirror_enterprise")
            return True
        except ImportError:
            return False
    if edition == "finance":
        try:
            importlib.import_module("docmirror_finance")
            return True
        except ImportError:
            return False
    return False


def _community_for_fallback(
    community_baseline: dict[str, Any] | None,
    result: ParseResult,
    detected_type: str,
    full_text: str,
) -> dict[str, Any] | None:
    """Reuse finalized community output when extended edition falls back."""
    if community_baseline is not None:
        return copy.deepcopy(community_baseline)
    return _run_community_extract(result, detected_type, full_text)


async def run_plugin_extract(
    result: ParseResult,
    *,
    edition: Edition = "community",
    full_text: str = "",
    file_path: str = "",
    community_baseline: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Match plugin by ``document_type``, run extract, return edition dict.

    Mirror ``ParseResult`` is not mutated during extract; post-extract hooks may apply audited mutations.
    """
    detected_type = getattr(result.entities, "document_type", "") or ""
    plugin_document_type = _plugin_document_type(result, detected_type)
    if plugin_document_type in _GENERIC_TYPES:
        logger.debug("[PluginRunner] Skip edition=%s: unclassified document", edition)
        return None

    if not _edition_package_available(edition):
        logger.debug("[PluginRunner] Edition package not installed: %s", edition)
        return None

    if edition == "community":
        out = _run_community_extract(result, plugin_document_type, full_text)
        if out is None and should_mirror_only(detected_type, "community"):
            out = _mirror_only_payload(result, detected_type, "community")
        if out is not None:
            return _finalize_extract(result, out, edition="community", detected_type=detected_type)
        return None

    out = await _run_extended_extract_async(
        result,
        edition,
        plugin_document_type,
        full_text,
        file_path,
        community_baseline=community_baseline,
    )
    if out is not None:
        from docmirror.plugins import registry

        plugin = registry.get(plugin_document_type, edition)
        if (
            edition in ("enterprise", "finance")
            and plugin is not None
            and getattr(plugin, "requires_license", False)
            and _LICENSE_WARNING not in (out.get("status") or {}).get("warnings", [])
        ):
            from docmirror.plugins.licensing.lifecycle import inject_edition_lifecycle_warnings

            out = inject_edition_lifecycle_warnings(out)
        return _finalize_extract(result, out, edition=edition, detected_type=detected_type, plugin=plugin)
    return None


def run_plugin_extract_sync(
    result: ParseResult,
    *,
    edition: Edition = "community",
    full_text: str = "",
    file_path: str = "",
    community_baseline: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Synchronous entry for CLI / output_builder."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            run_plugin_extract(
                result,
                edition=edition,
                full_text=full_text,
                file_path=file_path,
                community_baseline=community_baseline,
            )
        )

    container: list[dict[str, Any] | None] = []
    errors: list[BaseException] = []

    def _runner() -> None:
        try:
            container.append(
                asyncio.run(
                    run_plugin_extract(
                        result,
                        edition=edition,
                        full_text=full_text,
                        file_path=file_path,
                        community_baseline=community_baseline,
                    )
                )
            )
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(timeout=600)
    if errors:
        raise errors[0]
    return container[0] if container else None


def _run_community_extract(
    result: ParseResult,
    detected_type: str,
    full_text: str,
) -> dict[str, Any] | None:
    matched_plugin, matched_modname = find_premium_community_plugin(detected_type)

    if matched_plugin is not None:
        extract_fn = getattr(matched_plugin, "extract_from_mirror", None)
        if extract_fn is not None:
            try:
                result_data = extract_fn(result, full_text)
                data_block = result_data.get("data", {})
                records = data_block.get("records", [])
                fields = data_block.get("fields", {})
                total_rows = data_block.get("summary", {}).get("total_rows", len(records))
                if total_rows > 0 or fields:
                    return result_data
            except Exception as e:
                logger.error(
                    "Community plugin %s extract_from_mirror failed: %s",
                    matched_modname,
                    e,
                )

        try:
            domain_data = matched_plugin.build_domain_data(
                getattr(result.entities, "metadata", {}),
                getattr(result.entities, "entities", {}),
            )
        except Exception:
            domain_data = None

        if domain_data is not None:
            return _kv_community_payload(result, matched_plugin, detected_type, domain_data)

    if is_community_generic_enabled() and detected_type not in _GENERIC_TYPES:
        if not should_mirror_only(detected_type, "community"):
            generic_plugin, _gmod = get_generic_community_plugin()
            if generic_plugin is not None:
                from docmirror.plugins._base.generic_mirror_adapter import build_generic_community_output

                try:
                    return build_generic_community_output(result, detected_type, full_text)
                except Exception as e:
                    logger.error("[PluginRunner] generic community extract failed: %s", e)

    return None


def _kv_community_payload(result, matched_plugin, detected_type, domain_data) -> dict[str, Any]:
    from docmirror.models.edition_serializer import EditionContext, edition_serializer
    from docmirror.models.entities.domain_result import DomainQuality, normalize_domain_result
    from docmirror.plugins._base.dec_builder import dec_fields

    fields = dec_fields(domain_data)
    dec = normalize_domain_result(domain_data)
    if not dec.document_type or dec.document_type == "unknown":
        dec.document_type = detected_type
    warnings_list = ["no_fields_extracted"] if not fields else []
    dec.quality = DomainQuality(
        validation_passed=bool(fields),
        issues=[f"warning:{w}" for w in warnings_list],
    )

    ctx = EditionContext.from_finalize(
        result,
        detected_type=detected_type,
        edition="community",
        plugin=matched_plugin,
    )
    ctx.archetype = "key_value_document"
    ctx.match_method = "plugin_fallback"
    return edition_serializer(dec, context=ctx)


async def _run_extended_extract_async(
    result: ParseResult,
    edition: Edition,
    detected_type: str,
    full_text: str,
    file_path: str,
    *,
    community_baseline: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    from docmirror.plugins import registry

    plugin = registry.get(detected_type, edition)
    if plugin is None:
        return None

    if getattr(plugin, "requires_license", False) and not _is_edition_plugin_licensed(plugin):
        logger.info(
            "[PluginRunner] %s plugin %r has no valid license; degrading to community baseline",
            edition,
            detected_type,
        )
        community = _community_for_fallback(community_baseline, result, detected_type, full_text)
        if community is None:
            community = _mirror_only_payload(result, detected_type, "community")
        return _wrap_license_degraded(community, edition=edition, plugin=plugin)

    extract_fn = getattr(plugin, "extract", None)
    if extract_fn is not None:
        document_context = {
            "parse_result": result,
            "full_text": full_text,
            "detected_type": detected_type,
            "file_path": file_path or getattr(result, "file_path", "") or "",
        }
        try:
            if inspect.iscoroutinefunction(extract_fn):
                extracted = await extract_fn(document_context)
            else:
                extracted = extract_fn(document_context)
            if extracted and isinstance(extracted, dict):
                extracted["edition"] = edition
                return extracted
        except Exception as e:
            logger.warning("[%s] extract() failed for %s: %s", edition, detected_type, e)

    extract_mirror = getattr(plugin, "extract_from_mirror", None)
    if extract_mirror is not None:
        try:
            result_data = extract_mirror(result, full_text)
            data_block = result_data.get("data", {})
            records = data_block.get("records", [])
            total_rows = data_block.get("summary", {}).get("total_rows", len(records))
            if total_rows > 0:
                result_data["edition"] = edition
                return result_data
        except Exception as e:
            logger.warning("[%s] extract_from_mirror failed: %s", edition, e)

    community = _community_for_fallback(community_baseline, result, detected_type, full_text)
    if community is not None:
        cloned = copy.deepcopy(community)
        cloned["edition"] = edition
        cloned["metadata"]["parser"] = f"docmirror-{edition}"
        cloned.setdefault("plugins", {})[plugin.domain_name] = {
            "display_name": plugin.display_name,
            "edition": plugin.edition,
        }
        return cloned

    try:
        domain_data = plugin.build_domain_data(
            getattr(result.entities, "metadata", {}),
            getattr(result.entities, "entities", {}),
        )
    except Exception:
        domain_data = None

    if domain_data is not None:
        payload = _kv_community_payload(result, plugin, detected_type, domain_data)
        payload["edition"] = edition
        payload["metadata"]["parser"] = f"docmirror-{edition}"
        return payload

    return None
