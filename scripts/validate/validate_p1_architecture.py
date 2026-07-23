#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Enforce P1 convergence without adding a production architecture layer."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCMIRROR = ROOT / "docmirror"

CANONICAL_CAPABILITIES = (
    "generic",
    "bank_statement",
    "wechat_payment",
    "alipay_payment",
    "vat_invoice",
    "business_license",
    "credit_report",
)


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def main() -> int:
    errors: list[str] = []

    adr = ROOT / "docs/adr/0003-p1-core-stability-qualification.md"
    if not adr.is_file():
        errors.append("P1 stability ADR is missing")

    for retired in ("legacy_fact_patch.py", "runner.py", "core_extensions.py"):
        if (DOCMIRROR / "plugins/_runtime" / retired).exists():
            errors.append(f"retired pre-seal plugin runtime exists: {retired}")

    for domain in CANONICAL_CAPABILITIES:
        source = _source(f"docmirror/plugins/{domain}/community_plugin.py")
        inherited = domain in {"wechat_payment", "alipay_payment"}
        if "def recognize_facts(" not in source and not inherited:
            errors.append(f"{domain}: no fixed canonical enrichment implementation")

    plugin_api = _source("docmirror/plugin_api.py")
    for forbidden in ("DomainRecognizer", "FactPatch", "recognizers:"):
        if forbidden in plugin_api:
            errors.append(f"public Plugin API exposes pre-seal role: {forbidden}")
    for required in ("EditionProjector", "SealedParseResult", "projectors:"):
        if required not in plugin_api:
            errors.append(f"post-seal Plugin API is missing: {required}")

    enrichment = _source("docmirror/framework/middlewares/extraction/community_fact_recognizer.py")
    for domain in CANONICAL_CAPABILITIES:
        if f'"{domain}":' not in enrichment:
            errors.append(f"fixed canonical capability missing from Core map: {domain}")
    for forbidden in ("plugin_registry", "PluginProvider", "get_recognizer"):
        if forbidden in enrichment:
            errors.append(f"canonical enrichment crosses plugin runtime: {forbidden}")

    patch_source = _source("docmirror/input/canonical/fact_patch.py")
    for required in (
        "candidate = result.model_copy(deep=True)",
        "_apply_canonical_patch_in_place(candidate",
        "ParseResult.model_validate",
    ):
        if required not in patch_source:
            errors.append(f"CanonicalPatch application is not demonstrably transactional: {required}")

    fingerprint = _source("docmirror/models/fingerprint.py")
    for forbidden_field in ("parser_info", "mutations", "processing_time", "annex"):
        if f'"{forbidden_field}",' in fingerprint.split("_FACT_FIELDS", 1)[1].split(")", 1)[0]:
            errors.append(f"runtime/audit field participates in fact fingerprint: {forbidden_field}")

    mirror = _source("docmirror/output/mirror_projector.py")
    community = _source("docmirror/output/community_bundle.py")
    for name, source in (("Mirror", mirror), ("Community", community)):
        if "SealedParseResult" not in source or "to_read_view()" not in source:
            errors.append(f"{name} projector does not own its sealed read-view boundary")

    output_builder = _source("docmirror/server/output_builder.py")
    if "project_community_bundle(sealed.to_read_view()" in output_builder:
        errors.append("Output Builder unwraps the sealed result before Community projection")
    for function_name in ("build_community_projection", "build_extended_output", "build_all_projections"):
        function_source = output_builder[output_builder.index(f"def {function_name}(") :]
        next_function = function_source.find("\ndef ", 5)
        if next_function > 0:
            function_source = function_source[:next_function]
        if "expects SealedParseResult" not in function_source:
            errors.append(f"{function_name} does not reject mutable ParseResult")

    publish = _source(".github/workflows/publish.yml")
    if "validate_ci_green_window.py" in publish:
        errors.append("publish workflow still enforces the retired calendar-time gate")
    if "validate_release_commit_ci.py" not in publish:
        errors.append("publish workflow does not require successful CI for the exact release commit")
    if "validate_p1_stability_readiness.py --require-qualified" not in publish:
        errors.append("publish workflow does not enforce current technical P1 evidence")

    nightly = _source(".github/workflows/nightly-private.yml")
    if "validate_ga_6plus1.py --worker-matrix" not in nightly:
        errors.append("nightly P1 Golden does not enforce the [1,2,4] worker matrix")
    if "--classification-matrix" not in nightly:
        errors.append("nightly P1 Golden does not exercise automatic classification")
    if "validate_performance_baseline.py --require-approved" not in nightly:
        errors.append("nightly P1 gate does not enforce the approved performance/RSS baseline")

    if errors:
        print("P1 architecture qualification FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"P1 architecture qualification OK ({len(CANONICAL_CAPABILITIES)} canonical domains checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
