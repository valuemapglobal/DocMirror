# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Plugin Execution Contract (PEC) — unified plugin runner (Mirror layer之后).

Does **not** mutate ParseResult during extract; optional post-extract hooks may
mutate Mirror with ``record_mutation`` audit (see ``post_extract.yaml``).
See docs/design/08_middleware_layer_first_principles_redesign.md §5.4.
"""

from __future__ import annotations

import asyncio
import copy
import importlib
import inspect
import logging
import pkgutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from docmirror.models.entities.parse_result import ParseResult
from docmirror.plugins._base import build_classification_block
from docmirror.plugins.capability import should_mirror_only
from docmirror.plugins.discovery import find_community_plugin
from docmirror.plugins.post_extract.runner import run_post_extract_hooks

logger = logging.getLogger(__name__)

Edition = Literal["community", "enterprise", "finance"]

_GENERIC_TYPES = frozenset({"", "unknown", "generic"})
_LICENSE_WARNING = "_license_warning"
_MIRROR_ONLY_WARNING = "mirror_only:no_community_plugin"


def _premium_feature_name(domain_name: str) -> str:
    return f"{domain_name}_premium"


def _is_edition_plugin_licensed(plugin: Any) -> bool:
    """
    Check enterprise/finance license for plugins with ``requires_license=True``.

    Uses ``{domain}_premium`` feature names so community free-list domains
    (e.g. ``bank_statement``) do not bypass enterprise licensing.
    """
    if not getattr(plugin, "requires_license", False):
        return True

    premium = _premium_feature_name(plugin.domain_name)

    try:
        from docmirror.plugins.offline_license import offline_license_manager

        for license_file in offline_license_manager._licenses:
            if license_file.is_valid and premium in license_file.get_features():
                return True
    except Exception as exc:
        logger.debug("[PluginRunner] Offline license check failed: %s", exc)

    try:
        from docmirror.plugins.license import license_manager

        if license_manager.is_licensed(premium):
            return True
    except Exception as exc:
        logger.debug("[PluginRunner] Online license check failed: %s", exc)

    return False


def _wrap_license_degraded(
    community_payload: dict[str, Any],
    *,
    edition: Edition,
    plugin: Any,
) -> dict[str, Any]:
    """Community baseline for an edition output file with license degradation markers."""
    degraded = copy.deepcopy(community_payload)
    degraded["edition"] = edition
    degraded.setdefault("status", {}).setdefault("warnings", [])
    warnings = degraded["status"]["warnings"]
    if _LICENSE_WARNING not in warnings:
        warnings.insert(0, _LICENSE_WARNING)
    warnings.append(
        f"license_required:edition={edition},domain={getattr(plugin, 'domain_name', '')}"
    )
    degraded.setdefault("plugin", {})["license_required"] = True
    meta = degraded.setdefault("metadata", {})
    meta["parser"] = f"docmirror-{edition}"
    return degraded


def _finalize_extract(
    result: ParseResult,
    extracted: dict[str, Any],
    *,
    edition: Edition,
    detected_type: str,
    plugin: Any | None = None,
) -> dict[str, Any]:
    run_post_extract_hooks(
        result,
        extracted=extracted,
        edition=edition,
        document_type=detected_type,
        plugin=plugin,
    )
    return extracted


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


async def run_plugin_extract(
    result: ParseResult,
    *,
    edition: Edition = "community",
    full_text: str = "",
    file_path: str = "",
) -> dict[str, Any] | None:
    """
    Match plugin by ``document_type``, run extract, return edition dict.

    Mirror ``ParseResult`` is not mutated during extract; post-extract hooks may apply audited mutations.
    """
    detected_type = getattr(result.entities, "document_type", "") or ""
    if detected_type in _GENERIC_TYPES:
        logger.debug("[PluginRunner] Skip edition=%s: unclassified document", edition)
        return None

    if not _edition_package_available(edition):
        logger.debug("[PluginRunner] Edition package not installed: %s", edition)
        return None

    if edition == "community":
        out = _run_community_extract(result, detected_type, full_text)
        if out is None and should_mirror_only(detected_type, "community"):
            out = _mirror_only_payload(result, detected_type, "community")
        if out is not None:
            return _finalize_extract(
                result, out, edition="community", detected_type=detected_type
            )
        return None

    out = await _run_extended_extract_async(result, edition, detected_type, full_text, file_path)
    if out is not None:
        from docmirror.plugins import registry

        plugin = registry.get(detected_type, edition)
        return _finalize_extract(
            result, out, edition=edition, detected_type=detected_type, plugin=plugin
        )
    return None


def run_plugin_extract_sync(
    result: ParseResult,
    *,
    edition: Edition = "community",
    full_text: str = "",
    file_path: str = "",
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
                    )
                )
            )
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(timeout=120)
    if errors:
        raise errors[0]
    return container[0] if container else None


def _run_community_extract(
    result: ParseResult,
    detected_type: str,
    full_text: str,
) -> dict[str, Any] | None:
    matched_plugin, matched_modname = find_community_plugin(detected_type)

    if matched_plugin is not None:
        extract_fn = getattr(matched_plugin, "extract_from_mirror", None)
        if extract_fn is not None:
            try:
                result_data = extract_fn(result, full_text)
                data_block = result_data.get("data", {})
                records = data_block.get("records", [])
                total_rows = data_block.get("summary", {}).get("total_rows", len(records))
                if total_rows > 0:
                    return result_data
            except Exception as e:
                logger.error(
                    "Community plugin %s extract_from_mirror failed: %s",
                    matched_modname,
                    e,
                )

        import docmirror.plugins as _plugins_pkg

        if hasattr(matched_plugin, "extract_from_mirror"):
            for _, modname2, _ in pkgutil.iter_modules(_plugins_pkg.__path__):
                if (
                    modname2 == matched_modname
                    or not modname2.endswith("_community")
                    or modname2.startswith("_")
                ):
                    continue
                try:
                    mod2 = importlib.import_module(f"docmirror.plugins.{modname2}")
                except Exception:
                    continue
                if not hasattr(mod2, "plugin"):
                    continue
                fb = mod2.plugin
                fn = getattr(fb, "extract_from_mirror", None)
                if fn is None:
                    continue
                try:
                    fb_data = fn(result, full_text)
                    fb_records = fb_data.get("data", {}).get("records", [])
                    if len(fb_records) > 0:
                        fb_data.setdefault("document", {})["document_type"] = detected_type
                        fb_data.setdefault("classification", {})["matched_document_type"] = detected_type
                        fb_data["classification"]["matched"] = True
                        fb_data.setdefault("plugin", {})["name"] = detected_type
                        fb_data.setdefault("status", {}).setdefault("warnings", []).append(
                            f"fallback_from:{matched_modname}_to:{modname2}"
                        )
                        return fb_data
                except Exception:
                    continue

        try:
            domain_data = matched_plugin.build_domain_data(
                getattr(result.entities, "metadata", {}),
                getattr(result.entities, "entities", {}),
            )
        except Exception:
            domain_data = None

        if domain_data is not None:
            return _kv_community_payload(result, matched_plugin, detected_type, domain_data)

    return None


def _kv_community_payload(result, matched_plugin, detected_type, domain_data) -> dict[str, Any]:
    fields = {}
    if hasattr(domain_data, "raw_entities") and domain_data.raw_entities:
        fields = domain_data.raw_entities
    elif hasattr(domain_data, "to_dict"):
        d = domain_data.to_dict()
        d.pop("document_type", None)
        fields = {k: v for k, v in d.items() if v}

    file_path = getattr(result, "file_path", "")
    doc_name = Path(file_path).name if file_path else matched_plugin.display_name
    warnings_list = ["no_fields_extracted"] if not fields else []

    return {
        "schema_version": "2.0",
        "edition": "community",
        "document": {
            "document_type": detected_type,
            "document_name": doc_name,
            "domain": getattr(matched_plugin, "domain_name", detected_type),
            "archetype": "key_value_document",
            "language": "zh",
            "region": "CN",
            "source_format": "pdf",
            "page_count": len(getattr(result, "pages", [])),
            "properties": {},
        },
        "classification": build_classification_block(
            document_type=detected_type,
            domain=getattr(matched_plugin, "domain_name", detected_type),
            archetype="key_value_document",
            match_method="plugin_fallback",
            text="",
            scene_keywords=getattr(matched_plugin, "scene_keywords", ()),
        ),
        "status": {"success": True, "warnings": warnings_list, "errors": []},
        "plugin": {
            "name": matched_plugin.domain_name,
            "display_name": matched_plugin.display_name,
            "version": "community-2.0",
            "support_level": "L2",
        },
        "data": {
            "fields": fields,
            "records": [],
            "sections": [],
            "tables": [],
            "line_items": [],
            "summary": {
                "total_rows": 0,
                "total_income": 0.0,
                "total_expense": 0.0,
                "net_flow": 0.0,
                "period": {},
                "statistics": {
                    "income_count": 0,
                    "expense_count": 0,
                    "other_count": 0,
                    "avg_income": 0.0,
                    "avg_expense": 0.0,
                    "max_income": 0.0,
                    "max_expense": 0.0,
                },
            },
        },
        "plugins": {
            matched_plugin.domain_name: {
                "display_name": matched_plugin.display_name,
                "edition": matched_plugin.edition,
            }
        },
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "parser": "docmirror-community",
            "parser_version": "2.0.0",
            "task_id": "",
            "file_id": "",
        },
    }


async def _run_extended_extract_async(
    result: ParseResult,
    edition: Edition,
    detected_type: str,
    full_text: str,
    file_path: str,
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
        community = _run_community_extract(result, detected_type, full_text)
        if community is None:
            return None
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

    community = _run_community_extract(result, detected_type, full_text)
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
