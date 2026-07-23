# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic Core domain enrichment before the canonical seal."""

from __future__ import annotations

import importlib
import logging
import os
import threading
from typing import Any

from docmirror.configs.domain.registry import normalize_canonical_document_type
from docmirror.input.canonical.fact_patch import CanonicalPatch, apply_canonical_patch
from docmirror.models.entities.parse_result import ParseResult

from ..base import BaseMiddleware

logger = logging.getLogger(__name__)

_GENERIC_TYPES = frozenset({"", "unknown", "generic"})
_CANONICAL_CAPABILITIES = {
    "alipay_payment": "docmirror.plugins.alipay_payment.community_plugin:plugin",
    "bank_statement": "docmirror.plugins.bank_statement.community_plugin:plugin",
    "business_license": "docmirror.plugins.business_license.community_plugin:plugin",
    "credit_report": "docmirror.plugins.credit_report.community_plugin:plugin",
    "generic": "docmirror.plugins.generic.community_plugin:plugin",
    "vat_invoice": "docmirror.plugins.vat_invoice.community_plugin:plugin",
    "wechat_payment": "docmirror.plugins.wechat_payment.community_plugin:plugin",
}
CANONICAL_ENRICH_TIMEOUT_SECONDS = max(
    0.01,
    float(os.getenv("DOCMIRROR_CANONICAL_ENRICH_TIMEOUT_S", "300")),
)


def _canonical_document_type(result: ParseResult, detected_type: str) -> str:
    """Resolve a fixed Core capability from canonical classification evidence."""
    domain_specific = getattr(result.entities, "domain_specific", None)
    if isinstance(domain_specific, dict):
        forced = domain_specific.get("user_doc_type_hint")
        if forced and str(domain_specific.get("user_doc_type_hint_strength") or "prefer") == "force":
            return normalize_canonical_document_type(str(forced))
        hinted = domain_specific.get("canonical_document_type")
        if hinted:
            return normalize_canonical_document_type(str(hinted))
    mapped = normalize_canonical_document_type(detected_type)
    if mapped not in _GENERIC_TYPES:
        return mapped
    if isinstance(domain_specific, dict):
        scene = domain_specific.get("extractor_scene_hint") or domain_specific.get("pre_analyzer_scene_hint")
        confidence = float(domain_specific.get("extractor_scene_confidence") or 0.0)
        if scene and confidence >= 0.70:
            from_scene = normalize_canonical_document_type(str(scene))
            if from_scene not in _GENERIC_TYPES:
                return from_scene
    return mapped


def _load_canonical_capability(domain_name: str) -> Any | None:
    implementation = _CANONICAL_CAPABILITIES.get(domain_name)
    if implementation is None:
        implementation = _CANONICAL_CAPABILITIES["generic"]
    module_name, _, attribute = implementation.partition(":")
    return getattr(importlib.import_module(module_name), attribute, None)


def run_canonical_enrichment(result: ParseResult, *, full_text: str = "") -> CanonicalPatch:
    """Execute one fixed Core capability against an isolated read copy."""
    detected_type = str(getattr(result.entities, "document_type", "") or "")
    domain_name = _canonical_document_type(result, detected_type)
    selected_domain = domain_name if domain_name in _CANONICAL_CAPABILITIES else "generic"
    capability = _load_canonical_capability(selected_domain)
    recognize_facts = getattr(capability, "recognize_facts", None)
    if not callable(recognize_facts):
        return CanonicalPatch(
            capability_id=f"missing:{selected_domain}",
            reason="canonical capability unavailable",
        )

    read_view = result.model_copy(deep=True)
    returned: list[Any] = []
    failures: list[BaseException] = []

    def _invoke() -> None:
        try:
            returned.append(recognize_facts(read_view, full_text))
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(
        target=_invoke,
        name=f"docmirror-canonical-{selected_domain}",
        daemon=True,
    )
    worker.start()
    worker.join(CANONICAL_ENRICH_TIMEOUT_SECONDS)
    if worker.is_alive():
        logger.error(
            "[CanonicalEnrichment] capability %s timed out after %.2fs",
            selected_domain,
            CANONICAL_ENRICH_TIMEOUT_SECONDS,
        )
        return CanonicalPatch(
            capability_id=selected_domain,
            reason="canonical capability timed out without changing facts",
        )
    try:
        if failures:
            raise failures[0]
        if not returned:
            raise RuntimeError("canonical capability returned no value")
        return CanonicalPatch.model_validate(returned[0])
    except BaseException as exc:
        logger.error(
            "[CanonicalEnrichment] capability %s failed: %s",
            selected_domain,
            exc,
            exc_info=True,
        )
        return CanonicalPatch(
            capability_id=selected_domain,
            reason="canonical capability failed without changing facts",
        )


class CanonicalDomainEnricher(BaseMiddleware):
    """Apply fixed Core domain facts before validation and sealing."""

    DEPENDS_ON = ["EvidenceEngine"]
    PROVIDES = ["domain_entities", "domain_records", "sections"]

    def process(self, result: ParseResult) -> ParseResult:
        before = result.fact_fingerprint()
        patch = run_canonical_enrichment(
            result,
            full_text=result.full_text or result.raw_text,
        )
        result = apply_canonical_patch(result, patch)
        after = result.fact_fingerprint()
        if after != before:
            result.record_mutation(
                self.name,
                target_block_id="parse_result",
                field_changed="canonical_patch",
                old_value=before,
                new_value=after,
                confidence=patch.confidence,
                reason=f"applied CanonicalPatch from {patch.capability_id}",
            )
        return result


__all__ = ["CanonicalDomainEnricher", "run_canonical_enrichment"]
