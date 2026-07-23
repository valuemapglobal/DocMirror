#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Enforce P2 plugin-owned business resources without adding a runtime layer."""

from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "docmirror/plugins"

PROVIDERS = (
    "alipay_payment",
    "bank_statement",
    "business_license",
    "credit_report",
    "generic",
    "vat_invoice",
    "wechat_payment",
)

FORBIDDEN_CORE_RESOURCES = (
    "classification_rules.yaml",
    "document_field_schemas.yaml",
    "domain_contracts/community_core.yaml",
    "institution_registry.yaml",
    "key_synonyms.yaml",
    "layout_profiles.yaml",
    "ocr_corrections.yaml",
    "plugin_capability.yaml",
    "scene_keywords.yaml",
)

CONCRETE_DOMAINS = tuple(provider for provider in PROVIDERS if provider != "generic")


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def main() -> int:
    errors: list[str] = []
    manifests: dict[str, dict] = {}
    for provider in PROVIDERS:
        manifest_path = PLUGIN_ROOT / provider / "plugin.yaml"
        if not manifest_path.is_file():
            errors.append(f"missing plugin manifest: {provider}")
            continue
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        manifests[provider] = manifest
        declared_provider = manifest.get("provider") or {}
        if declared_provider.get("id") != provider or declared_provider.get("domain_name") != provider:
            errors.append(f"manifest identity mismatch: {provider}")
        for name, relative_value in (manifest.get("resources") or {}).items():
            relative = PurePosixPath(str(relative_value or ""))
            if relative.is_absolute() or ".." in relative.parts:
                errors.append(f"unsafe resource path: {provider}.{name}={relative_value}")
                continue
            if not (PLUGIN_ROOT / provider / Path(*relative.parts)).is_file():
                errors.append(f"missing plugin resource: {provider}.{name}={relative_value}")

    yaml_root = ROOT / "docmirror/configs/yaml"
    for relative in FORBIDDEN_CORE_RESOURCES:
        if (yaml_root / relative).exists():
            errors.append(f"business resource remains in Core configs: {relative}")

    for relative in (
        "docmirror/layout/scene/evidence_engine.py",
        "docmirror/output/community_bundle.py",
    ):
        source = _source(relative)
        for domain in CONCRETE_DOMAINS:
            if domain in source:
                errors.append(f"concrete-domain branch remains: {relative}: {domain}")

    registry_source = _source("docmirror/plugins/_runtime/plugin_registry.py")
    for provider in CONCRETE_DOMAINS:
        static_import = f"docmirror.plugins.{provider}.community_plugin"
        if static_import in registry_source:
            errors.append(f"static built-in registration remains: {static_import}")

    correction_source = _source("docmirror/ocr/correction/packs.py")
    if "OCR_CORRECTIONS_YAML" in correction_source:
        errors.append("OCR correction registry still reads the central business pack")

    post_extract = _source("docmirror/configs/yaml/post_extract.yaml")
    if "document_type ==" in post_extract:
        errors.append("generic post-extract catalog still contains a business-domain guard")

    for obsolete_schema in (
        "bank_statement_schema.py",
        "credit_report_schema.py",
        "table_payment_schema.py",
    ):
        if (ROOT / "docmirror/models/schemas" / obsolete_schema).exists():
            errors.append(f"business DEC schema remains in Core models: {obsolete_schema}")

    for obsolete_runtime in (
        "docmirror/framework/middlewares/extraction/entity_extractor.py",
        "docmirror/layout/scene/institution_hint.py",
    ):
        if (ROOT / obsolete_runtime).exists():
            errors.append(f"obsolete business runtime remains: {obsolete_runtime}")

    migrated_literals = {
        "docmirror/framework/middlewares/validation/anomaly_detector.py": (
            "credit_accounts",
            "credit_account_collapse",
            "开立日期",
            "借款金额",
        ),
        "docmirror/plugins/_runtime/core_extensions.py": ("docmirror.plugins.credit_report",),
        "docmirror/ocr/local_structure/candidate_supplement.py": (
            "docmirror.layout.segment.page_blocks",
            "detect_pre_grid_field_supplements",
        ),
        "docmirror/ocr/local_structure/build.py": ("credit_closed_account_block", "还款记录"),
        "docmirror/ocr/field_grid/bands.py": ("账户关闭日期", "还款期数"),
        "docmirror/ocr/field_grid/assemble.py": ("账户关闭日期", "借款金额"),
        "docmirror/models/schemas/domain_contract_validator.py": ("交易订单号", "对方户名"),
        "docmirror/output/markdown_renderer.py": ("_PAYMENT_DIRECTION_VALUES", "不计收支"),
        "docmirror/output/community_bundle.py": ("credit_summary =", 'public_name == "transactions"'),
        "docmirror/layout/scene/evidence_engine.py": ("交易订单号", "商家订单号"),
        "docmirror/layout/vocabulary.py": ("交易日期", "对方户名", "借贷标志"),
        "docmirror/tables/row_kind.py": ("借方发生额", "本对账期末余额", "记账日"),
        "docmirror/tables/structure_detect/pipe_grid.py": ("借方发生额", "本对账期末余额", "记账日"),
        "docmirror/tables/structure_detect/pipe_table_builder.py": ("借方发生额", "本对账期末余额"),
        "docmirror/tables/char/semantic_column_mapper.py": ("交易日期", "对方户名", "发生额"),
        "docmirror/tables/table_structure_fix.py": ("发生额", "余额", "存入"),
        "docmirror/topology/page.py": ("借方发生额", "贷方发生额", "出单截止日期"),
        "docmirror/quality/aggregator.py": CONCRETE_DOMAINS,
    }
    for relative, literals in migrated_literals.items():
        source = _source(relative)
        for literal in literals:
            if literal in source:
                errors.append(f"plugin-owned business literal remains: {relative}: {literal}")

    required_bank_resources = {
        "institutions",
        "table_styles",
        "ocr_corrections",
        "post_extract",
    }
    bank_resources = set((manifests.get("bank_statement", {}).get("resources") or {}).keys())
    missing_bank = required_bank_resources - bank_resources
    if missing_bank:
        errors.append(f"bank vertical resource ownership incomplete: {sorted(missing_bank)}")

    generic_resources = set((manifests.get("generic", {}).get("resources") or {}).keys())
    missing_generic = {"classification_rules", "layout_profiles", "scanned_statement_profile"} - generic_resources
    if missing_generic:
        errors.append(f"generic plugin resource ownership incomplete: {sorted(missing_generic)}")
    generic_layout = PLUGIN_ROOT / "generic/resources/layout_profiles.yaml"
    if generic_layout.is_file():
        layout_payload = yaml.safe_load(generic_layout.read_text(encoding="utf-8")) or {}
        semantics = layout_payload.get("table_semantics") or {}
        for required in ("column_keywords", "pipe_grid", "summary_fields", "value_type_patterns"):
            if required not in semantics:
                errors.append(f"generic table semantics missing: {required}")

    credit_manifest = manifests.get("credit_report", {})
    credit_fact_outputs = set((credit_manifest.get("fact_outputs") or {}).get("datasets") or ())
    required_credit_facts = {
        "credit_accounts",
        "credit_lines",
        "repayment_records",
        "overdue_records",
        "inquiry_records",
        "public_records",
    }
    if missing_credit_facts := required_credit_facts - credit_fact_outputs:
        errors.append(f"credit FactPatch manifest omits datasets: {sorted(missing_credit_facts)}")

    if errors:
        print("P2 plugin-first architecture validation FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"P2 plugin-first architecture validation OK ({len(manifests)} manifests checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
