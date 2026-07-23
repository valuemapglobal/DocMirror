#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Enforce P1 convergence without adding a production architecture layer."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCMIRROR = ROOT / "docmirror"

RECOGNIZERS = (
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

    if (DOCMIRROR / "plugins/_runtime/legacy_fact_patch.py").exists():
        errors.append("legacy edition-envelope-to-FactPatch adapter exists")

    for domain in RECOGNIZERS:
        source = _source(f"docmirror/plugins/{domain}/community_plugin.py")
        inherited = domain in {"wechat_payment", "alipay_payment"}
        if "def recognize_facts(" not in source and not inherited:
            errors.append(f"{domain}: no native recognize_facts implementation")

    plugin_api = _source("docmirror/plugin_api.py")
    if "-> FactPatch | None" in plugin_api or "-> FactPatch:" not in plugin_api:
        errors.append("DomainRecognizer contract is not FactPatch-only")

    runner = _source("docmirror/plugins/_runtime/runner.py")
    recognition = runner[runner.index("def run_fact_recognition_sync(") : runner.index("def _kv_community_payload(")]
    for forbidden in ("legacy_payload_to_fact_patch", "_run_community_recognition", "edition_serializer"):
        if forbidden in recognition:
            errors.append(f"canonical recognizer runner contains legacy/delivery path: {forbidden}")

    patch_source = _source("docmirror/input/canonical/fact_patch.py")
    for required in (
        "candidate = result.model_copy(deep=True)",
        "_apply_fact_patch_in_place(candidate",
        "ParseResult.model_validate",
    ):
        if required not in patch_source:
            errors.append(f"FactPatch application is not demonstrably transactional: {required}")

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
    if "validate_performance_baseline.py --require-approved" not in nightly:
        errors.append("nightly P1 gate does not enforce the approved performance/RSS baseline")

    if errors:
        print("P1 architecture qualification FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"P1 architecture qualification OK ({len(RECOGNIZERS)} recognizer domains checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
