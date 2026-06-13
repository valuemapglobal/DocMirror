# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Domain Plugin Bridge Middleware
===============================

Generic bridge middleware that connects DocMirror's unified pipeline to all DomainPlugins.
Eliminates boilerplate middleware code by handling invocation, sync/async conversion, and 
context assembly automatically based on the resolved `document_type`.
"""

import asyncio
import inspect
import logging
import re
from typing import Any, Dict

from docmirror.middlewares.base import BaseMiddleware
from docmirror.middlewares.registry import register_middleware
from docmirror.models.entities.parse_result import ParseResult
from docmirror.plugins import registry

logger = logging.getLogger(__name__)


@register_middleware("DomainPluginBridge", order=10)
class DomainPluginBridge(BaseMiddleware):
    """
    Generic bridge middleware for executing DomainPlugins.

    Responsibilities:
        1. Identifies the document_type from ParseResult.
        2. Retrieves the corresponding domain plugin from PluginRegistry.
        3. Builds a standardized document_context (text, pages, file).
        4. Calls plugin.match() to verify suitability.
        5. Calls plugin.extract() to perform domain-specific extraction.
        6. Injects the results into result.entities.domain_specific.
    """

    DEPENDS_ON = []
    PROVIDES = ["domain_specific_entities", "structured_data"]

    def process(self, result: ParseResult) -> ParseResult:
        doc_type = result.entities.document_type

        document_context = self._build_document_context(result)
        detected_plugin = None

        # If document_type is empty or generic, try to auto-detect using plugin.match()
        if not doc_type or doc_type == "generic" or doc_type == "unknown":
            logger.debug("[DomainPluginBridge] Document type unknown/generic, attempting auto-discovery")
            # Force auto-discovery of all builtin plugins just in case
            registry._ensure_discovered()
            seen_domains = set()
            for (domain_ed, ed), plugin in sorted(registry._plugins.items()):
                if domain_ed in seen_domains:
                    continue
                seen_domains.add(domain_ed)
                if plugin.match(document_context):
                    doc_type = domain_ed
                    detected_plugin = plugin
                    result.entities.document_type = doc_type
                    logger.info(f"[DomainPluginBridge] Auto-discovered document type: '{doc_type}'")
                    break

            if not detected_plugin:
                logger.debug("[DomainPluginBridge] Skip: No plugin matched the document context")
                return result
        else:
            detected_plugin = registry.get_first(doc_type)
            if not detected_plugin:
                logger.debug(f"[DomainPluginBridge] Skip: No plugin registered for document_type '{doc_type}'")
                return result

            if not detected_plugin.match(document_context):
                logger.info(
                    f"[DomainPluginBridge] Plugin '{detected_plugin.domain_name}' match() returned False; "
                    "attempting auto-discovery"
                )
                detected_plugin = None
                seen_domains = set()
                for (domain_ed, ed), plugin in sorted(registry._plugins.items()):
                    if domain_ed in seen_domains:
                        continue
                    seen_domains.add(domain_ed)
                    if plugin.match(document_context):
                        doc_type = domain_ed
                        detected_plugin = plugin
                        result.entities.document_type = doc_type
                        logger.info(f"[DomainPluginBridge] Auto-discovered after mismatch: '{doc_type}'")
                        break
                if not detected_plugin:
                    return result

        logger.info(f"[DomainPluginBridge] ▶ Starting extraction for domain '{doc_type}' via {detected_plugin.display_name} (edition={getattr(detected_plugin, 'edition', 'community')})")

        # Edition / license check: enterprise plugins need valid license
        edition = getattr(detected_plugin, "edition", "community")
        requires_license = getattr(detected_plugin, "requires_license", False)
        if edition == "enterprise" and requires_license:
            if not self._check_plugin_license(detected_plugin):
                logger.info(f"[DomainPluginBridge] Enterprise plugin '{doc_type}' has no valid license; returning community baseline")
                return self._fallback_community_baseline(result, detected_plugin, doc_type)

        try:
            document_context = self._build_document_context(result)
            extracted = self._invoke_plugin(detected_plugin, document_context)
            self._inject_extracted_data(result, extracted)

            domain_keys = list(getattr(result.entities, "domain_specific", {}).keys())
            logger.info(f"[DomainPluginBridge] ◀ Complete | domain_specific_keys={domain_keys}")
        except Exception as e:
            logger.error(f"[DomainPluginBridge] Extraction failed for domain '{doc_type}': {e}", exc_info=True)

        return result

    def _build_document_context(self, result: ParseResult) -> dict[str, Any]:
        """Build standardized execution context for the plugin."""
        rebuilt = getattr(result, "full_text", "") or ""
        extractor_text = getattr(result, "extractor_full_text", "") or ""
        # Prefer richer CoreExtractor text when rebuild drops table body lines.
        plugin_text = extractor_text if len(extractor_text) > len(rebuilt) else rebuilt
        if extractor_text and plugin_text == rebuilt and "交易日期" not in rebuilt and "交易日期" in extractor_text:
            plugin_text = extractor_text
        # Ledger scan: rebuilt full_text may merge txn lines; prefer extractor when it keeps more dates.
        if extractor_text:
            merged_txn_line = re.compile(r"\d{4}-\d{2}-\d{2}[^\n]*\d{4}-\d{2}-\d{2}")
            if merged_txn_line.search(rebuilt or "") and not merged_txn_line.search(extractor_text):
                plugin_text = extractor_text
            else:
                date_hits = lambda t: len(re.findall(r"(?m)^\d{4}-\d{2}-\d{2}", t or ""))
                if date_hits(extractor_text) > date_hits(rebuilt):
                    plugin_text = extractor_text

        context = {
            "text": plugin_text,
            "file": str(getattr(result, "file_path", "unknown")),
            "type": result.entities.document_type,
            "parse_result": result,
            "pages": [],
        }

        if hasattr(result, "pages"):
            texts = []
            for page in result.pages:
                page_text = "\n".join([b.content for b in page.texts if hasattr(b, "content")]) if hasattr(page, "texts") else ""
                texts.append(page_text)

                # Pages array for backward compatibility with plugins like real_estate_certificate
                context["pages"].append({
                    "text": page_text,
                    "tables": [],
                })

            # If standard full_text is empty, fallback to aggregated bounding box texts
            if not context["text"]:
                context["text"] = "\n".join(texts)

        return context

    def _invoke_plugin(self, plugin, document_context: dict[str, Any]) -> dict[str, Any]:
        """Invoke plugin extraction safely handling synchronous and asynchronous implementations."""
        if inspect.iscoroutinefunction(plugin.extract):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # Cannot use run_until_complete inside active loop on current thread
                import threading
                ret = None
                exc = None

                def _run_in_thread():
                    nonlocal ret, exc
                    try:
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        ret = new_loop.run_until_complete(plugin.extract(document_context))
                        new_loop.close()
                    except Exception as e:
                        exc = e

                thread = threading.Thread(target=_run_in_thread)
                thread.start()
                thread.join()

                if exc:
                    raise exc
                return ret or {}
            else:
                new_loop = asyncio.new_event_loop()
                try:
                    return new_loop.run_until_complete(plugin.extract(document_context))
                finally:
                    new_loop.close()
        else:
            return plugin.extract(document_context)

    @staticmethod
    def _check_plugin_license(plugin) -> bool:
        """Check whether an enterprise plugin has a valid license.

        Uses OfflineLicenseManager if available; otherwise defaults to
        allowing extraction (no license enforcement in open-source runtime).
        """
        try:
            from docmirror.plugins.offline_license import OfflineLicenseManager
            mgr = OfflineLicenseManager()
            return mgr.is_licensed(plugin.domain_name)
        except ImportError:
            # No license manager — running in open-source mode, skip license check
            return False
        except Exception:
            logger.debug("[DomainPluginBridge] License check failed; denying enterprise extraction")
            return False

    @staticmethod
    def _fallback_community_baseline(result, plugin, doc_type):
        """Fall back to community edition build_domain_data when enterprise license is missing."""
        metadata = getattr(result.entities, "domain_specific", {}) or {}
        entities = getattr(result.entities, "domain_specific", {}) or {}
        # Use community edition identity_fields via scene_keywords-based extraction
        if hasattr(plugin, "scene_keywords"):
            logger.info(f"[DomainPluginBridge] Community baseline for '{doc_type}' — identity fields only")
        # Mark as unlicensed in output
        if not hasattr(result.entities, "domain_specific") or result.entities.domain_specific is None:
            result.entities.domain_specific = {}
        result.entities.domain_specific["_edition"] = "community"
        result.entities.domain_specific["_requires_license"] = True
        return result

    @staticmethod
    def _maybe_rebuild_bank_table(result: ParseResult, extracted: dict[str, Any]) -> None:
        if (result.entities.document_type or "") != "bank_statement":
            return
        structured = extracted.get("structured_data") or {}
        transactions = structured.get("transactions") or []
        if not transactions:
            return
        try:
            from docmirror_enterprise.plugins.bank_statement.table_rebuild import rebuild_bank_table_from_transactions
        except ImportError:
            from docmirror.plugins.bank_statement.table_rebuild import rebuild_bank_table_from_transactions

        if rebuild_bank_table_from_transactions(result, transactions):
            logger.info(
                "[DomainPluginBridge] Rebuilt bank ledger table from %d transactions",
                len(transactions),
            )
            from docmirror.core.extraction.provenance_stamps import stamp_mirror_block_provenance

            stamp_mirror_block_provenance(result)

    @staticmethod
    def _maybe_attach_credit_sections(result: ParseResult) -> None:
        """Populate ParseResult.sections for L6 DocGraph / UDIF relations."""
        if (result.entities.document_type or "") != "credit_report":
            return
        if result.sections:
            return
        text = getattr(result, "extractor_full_text", "") or getattr(result, "full_text", "") or ""
        if not text.strip():
            return
        try:
            try:
                from docmirror_enterprise.plugins.credit_report.extractors.section_splitter import SectionSplitter
            except ImportError:
                from docmirror.plugins.credit_report.extractors.section_splitter import SectionSplitter

            splitter = SectionSplitter()
            report_type = (result.entities.domain_specific or {}).get("report_subtype")
            if not report_type:
                report_type = splitter.detect_report_type(text)
            sections_dict = splitter.split(text, report_type)
            result.sections = [
                {
                    "id": f"sec_{i}",
                    "title": title,
                    "name": title,
                    "page_start": 1,
                }
                for i, (title, content) in enumerate(sections_dict.items())
                if title.strip() or (content or "").strip()
            ]
            if result.sections:
                logger.debug(
                    "[DomainPluginBridge] Attached %d credit report sections for L6 graph",
                    len(result.sections),
                )
        except Exception as exc:
            logger.debug("[DomainPluginBridge] credit sections skip: %s", exc)

    def _inject_extracted_data(self, result: ParseResult, extracted: dict[str, Any]) -> None:
        """Dynamically inject extracted metadata into the Domain Specific structure."""
        from docmirror.models.entities.domain_result import normalize_domain_result

        if not extracted:
            return

        domain_result = normalize_domain_result(extracted)

        if not hasattr(result.entities, "domain_specific") or result.entities.domain_specific is None:
            result.entities.domain_specific = {}

        # Inject normalized entities
        result.entities.domain_specific.update(domain_result.entities)

        # Sync wrapper fields
        for ext_field in ["structured_data", "derived_variables"]:
            val = getattr(domain_result, ext_field, None)
            if val is not None:
                result.entities.domain_specific[ext_field] = val

        self._maybe_rebuild_bank_table(result, extracted)
        self._maybe_attach_credit_sections(result)

        # Merge properties into domain_specific (backward compatible API)
        for k, v in domain_result.properties.items():
            if k not in result.entities.domain_specific:
                result.entities.domain_specific[k] = v

        quality = domain_result.quality
        plugin_conf = quality.confidence
        if plugin_conf and plugin_conf > result.confidence:
            result.confidence = plugin_conf

        if quality.trust_score:
            try:
                from docmirror.models.entities.parse_result import TrustResult
                result.trust = TrustResult(
                    trust_score=quality.trust_score,
                    validation_score=quality.field_coverage,
                    validation_passed=quality.validation_passed,
                )
            except Exception as e:
                logger.debug(f"[DomainPluginBridge] Could not update TrustResult: {e}")

        # Final structural cleanup: Scrub 1-column illusory tables from result pages before serialization
        from docmirror.core.table.table_column_utils import effective_table_column_count

        for page in result.pages:
            if hasattr(page, "tables"):
                scrubbed_tables = []
                for t in page.tables:
                    if effective_table_column_count(t) >= 2:
                        scrubbed_tables.append(t)
                page.tables.clear()
                page.tables.extend(scrubbed_tables)
