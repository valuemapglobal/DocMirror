# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Plugin Execution Contract (PEC) — unified plugin runner after Mirror extraction.

Orchestrates canonical Community recognition and read-only extended projection:
match plugin by ``document_type``, run ``recognize`` / ``extract`` /
``build_domain_data``, normalize through DEC validation, serialize edition JSON,
then invoke post-extract hooks. Community recognition enriches the existing
``ParseResult`` zones; edition projectors read that same ParseResult directly.

Pipeline role: Community recognition may enrich ParseResult's existing zones;
output building invokes requested edition projectors with that ParseResult.

Key exports: ``run_plugin_extract``, ``run_plugin_extract_sync``.

Dependencies: ``community`` (discovery), ``post_extract.runner`` (hooks),
``licensing.entitlements`` / ``licensing.lifecycle`` (edition gating),
``models.edition_serializer``, ``models.entities.domain_result``.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from docmirror.models.entities.parse_result import ParseResult
from docmirror.plugins._base import build_classification_block
from docmirror.plugins._runtime.community import (
    find_premium_community_plugin,
    get_generic_community_plugin,
    is_community_generic_enabled,
    normalize_premium_document_type,
)
from docmirror.plugins._runtime.post_extract.runner import run_post_extract_hooks

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
    from docmirror.plugins._runtime.licensing.contract import premium_feature

    return premium_feature(domain_name)


def _is_edition_plugin_licensed(plugin: Any) -> bool:
    """
    Check enterprise/finance license for plugins with ``requires_license=True``.

    Delegates to ``licensing.entitlements.is_entitled`` (SSOT).
    """
    if not getattr(plugin, "requires_license", False):
        return True

    from docmirror.plugins._runtime.licensing.entitlements import is_entitled

    return is_entitled(getattr(plugin, "domain_name", "") or "")


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


def _basic_parse_result_projection(result: ParseResult, edition: Edition) -> dict[str, Any]:
    """Build an explicit degraded edition from ParseResult without an intermediate model."""
    extension = dict(result.entities.domain_specific or {})
    fields = {
        key: value
        for key, value in extension.items()
        if not key.startswith("_") and not isinstance(value, (dict, list))
    }
    datasets = {
        key: value
        for key, value in extension.items()
        if not key.startswith("_")
        and isinstance(value, list)
        and value
        and all(isinstance(item, dict) for item in value)
    }
    return {
        "schema_version": "2.2.0",
        "edition": edition,
        "document": {
            "document_type": str(result.entities.document_type or "generic"),
            "document_name": Path(result.file_path).name if result.file_path else "",
            "page_count": result.page_count,
        },
        "data": {
            "fields": fields,
            "sections": [section.model_dump(mode="json", exclude_none=True) for section in result.sections],
            "tables": [],
            **datasets,
        },
        "status": {
            "success": result.success,
            "warnings": list(result.parser_info.warnings),
            "errors": list(result.errors),
        },
        "metadata": {"parser": f"docmirror-{edition}", "source": "parse_result"},
        "plugin": {"name": str(result.entities.document_type or "generic")},
    }


def _attach_source_file_path(result: ParseResult, file_path: str) -> None:
    """Record source path in ParseResult provenance for every projector."""
    if not file_path or result.file_path:
        return
    from docmirror.models.entities.parse_result import ProvenanceInfo

    if result.provenance is None:
        result.provenance = ProvenanceInfo(file_path=file_path)
    else:
        result.provenance.file_path = file_path


async def run_plugin_extract(
    result: ParseResult,
    *,
    edition: Edition = "community",
    full_text: str = "",
    file_path: str = "",
    on_progress: Callable[[str, float, str], None] | None = None,
) -> dict[str, Any] | None:
    """
    Match plugin by ``document_type``, run extract, return edition dict.

    Community recognition enriches ParseResult; extended editions read ParseResult.
    """
    detected_type = getattr(result.entities, "document_type", "") or ""
    plugin_document_type = _plugin_document_type(result, detected_type)
    # Community's +1 plugin is the universal safety net, including genuinely
    # unclassified documents.  Extended editions still require a concrete
    # domain plugin and therefore keep the old skip behavior.
    if plugin_document_type in _GENERIC_TYPES and edition != "community":
        logger.debug("[PluginRunner] Skip edition=%s: unclassified document", edition)
        return None

    if not _edition_package_available(edition):
        logger.debug("[PluginRunner] Edition package not installed: %s", edition)
        return None

    if edition == "community":
        if on_progress:
            from docmirror.plugins._runtime.plugin_registry import registry

            registry.set_progress_callback(on_progress)
        out = _run_community_recognition(result, plugin_document_type, full_text)
        if out is not None:
            finalized = _finalize_extract(result, out, edition="community", detected_type=detected_type)
            from docmirror.plugins._runtime.parse_result_enrichment import (
                merge_plugin_projection_into_parse_result,
            )

            merge_plugin_projection_into_parse_result(result, finalized)
            return finalized
        return None

    else:
        out = await _run_extended_extract_async(
            result,
            edition,
            plugin_document_type,
        )
        if out is None:
            return None
        from docmirror.plugins._runtime import registry

        plugin = registry.get(plugin_document_type, edition)
        if (
            edition in ("enterprise", "finance")
            and plugin is not None
            and getattr(plugin, "requires_license", False)
            and _LICENSE_WARNING not in (out.get("status") or {}).get("warnings", [])
        ):
            from docmirror.plugins._runtime.licensing.lifecycle import inject_edition_lifecycle_warnings

            out = inject_edition_lifecycle_warnings(out)
        return _finalize_extract(result, out, edition=edition, detected_type=detected_type, plugin=plugin)


def run_plugin_extract_sync(
    result: ParseResult,
    *,
    edition: Edition = "community",
    full_text: str = "",
    file_path: str = "",
    on_progress: Callable[[str, float, str], None] | None = None,
) -> dict[str, Any] | None:
    """Synchronous entry for CLI / output_builder (GA1.0-RUNNER-01).

    Fix: Avoid ``asyncio.run()`` when inside an existing event loop (Python 3.12
    ``loop.shutdown_default_executor()`` hangs).  Use a dedicated event loop via
    ``new_event_loop`` + ``run_until_complete`` + ``close`` in ALL contexts
    — never call ``asyncio.run()``, which hangs in Python 3.12 ThreadPoolExecutor
    threads during ``shutdown_default_executor()``.
    """

    def _run_coro_in_new_loop(
        c: asyncio.Future[dict[str, Any] | None],
    ) -> dict[str, Any] | None:
        """Run a coroutine in a fresh event loop, then tear down cleanly.

        Never calls ``asyncio.run()`` because ``loop.shutdown_default_executor()``
        hangs in Python 3.12 when the coroutine spawns executor-backed tasks.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(c)
        finally:
            try:
                _cancel_all_tasks(loop)
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            finally:
                loop.close()

    coro = run_plugin_extract(
        result,
        edition=edition,
        full_text=full_text,
        file_path=file_path,
        on_progress=on_progress,
    )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running event loop (e.g. ThreadPoolExecutor threads).
        # Run directly in the same thread — never asyncio.run().
        return _run_coro_in_new_loop(coro)

    # Has a running event loop (main thread).  Spawn a separate thread
    # with a dedicated loop so we never nest loops.
    _container: list[dict[str, Any] | None] = []
    _errors: list[BaseException] = []

    def _runner() -> None:
        try:
            _container.append(_run_coro_in_new_loop(coro))
        except BaseException as exc:
            _errors.append(exc)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(timeout=600)
    if _errors:
        raise _errors[0]
    return _container[0] if _container else None


def _cancel_all_tasks(loop: asyncio.AbstractEventLoop) -> None:
    """Cancel all pending tasks in *loop* so shutdown never blocks."""
    pending = asyncio.all_tasks(loop)
    if not pending:
        return
    for task in pending:
        task.cancel()
    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))


def _run_community_recognition(
    result: ParseResult,
    detected_type: str,
    full_text: str,
) -> dict[str, Any] | None:
    matched_plugin, matched_modname = find_premium_community_plugin(detected_type)

    if matched_plugin is not None:
        recognize_fn = getattr(matched_plugin, "recognize", None)
        if recognize_fn is not None:
            try:
                result_data = recognize_fn(result, full_text)
                data_block = result_data.get("data", {})
                records = data_block.get("records", [])
                fields = data_block.get("fields", {})
                total_rows = data_block.get("summary", {}).get("total_rows", len(records))
                has_structured_content = any(
                    bool(value) for key, value in data_block.items() if key not in {"summary", "fields", "records"}
                )
                if total_rows > 0 or fields or has_structured_content:
                    return result_data
            except Exception as e:
                logger.error(
                    "Community plugin %s recognize failed: %s",
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

    if is_community_generic_enabled():
        generic_plugin, _gmod = get_generic_community_plugin()
        if generic_plugin is not None:
            from docmirror.plugins._base.generic_community_adapter import build_generic_community_output

            try:
                generic_type = detected_type if detected_type not in {"", "unknown"} else "generic"
                return build_generic_community_output(result, generic_type, full_text)
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
) -> dict[str, Any] | None:
    from docmirror.plugins._runtime import registry

    plugin = registry.get(detected_type, edition)
    if plugin is None:
        logger.warning("[%s] No plugin found for detected_type=%s", edition, detected_type)
        return None

    if getattr(plugin, "requires_license", False) and not _is_edition_plugin_licensed(plugin):
        logger.info(
            "[%s] Plugin %s requires license but is not entitled — no projection",
            edition,
            detected_type,
        )
        return None

    extract_fn = getattr(plugin, "extract", None)
    if extract_fn is not None:
        try:
            if inspect.iscoroutinefunction(extract_fn):
                extracted = await extract_fn(result)
            else:
                extracted = extract_fn(result)
            if extracted and isinstance(extracted, dict):
                extracted["edition"] = edition
                return extracted
            else:
                logger.warning(
                    "[%s] extract() returned non-dict: %s (type=%s)",
                    edition,
                    detected_type,
                    type(extracted).__name__ if extracted is not None else "None",
                )
        except Exception as e:
            import traceback

            logger.error(
                "[%s] 🔥 extract() EXCEPTION for %s: %s\n%s", edition, detected_type, e, traceback.format_exc()
            )

    logger.info(
        "[%s] projector failed for %s — using basic ParseResult projection",
        edition,
        detected_type,
    )
    basic = _basic_parse_result_projection(result, edition)
    basic.setdefault("plugins", {})[plugin.domain_name] = {
        "display_name": plugin.display_name,
        "edition": plugin.edition,
    }
    return basic
