# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Evidence coverage denominator is derived from plugin domain contracts."""

from __future__ import annotations

from docmirror.quality.evidence_coverage import get_key_fields_for_domain


def _priorities(domain: str) -> dict[str, str]:
    return {field.field_path: field.priority for field in get_key_fields_for_domain(domain)}


def test_required_and_optional_contract_fields_define_evidence_priorities() -> None:
    bank = _priorities("bank_statement")
    assert bank["account_number"] == "P0"
    assert bank["transaction_date"] == "P0"
    assert bank["currency"] == "P1"
    assert bank["counter_party"] == "P1"


def test_contract_alias_and_generic_fallback_are_resource_driven() -> None:
    assert _priorities("credit_report_enterprise") == _priorities("credit_report")
    assert _priorities("uninstalled_domain") == _priorities("generic")
