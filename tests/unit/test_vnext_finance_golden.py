# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult
from docmirror.models.mirror.domain_access import local_structure_evidence_pages_from_domain_specific
from docmirror.models.mirror.page_evidence_bundles import domain_specific_with_page_bundles, page_evidence_bundle
from docmirror.ocr.local_structure import extract_local_structure_evidence
from docmirror.plugins._base.kv_community_enrich import enrich_credit_report_output
from docmirror.plugins.credit_report.account_structure import extract_credit_accounts_from_local_structure_evidence

_FIXTURE = Path("tests/fixtures/scanned/account_card_page4_full_layout.json")
_GOLDEN = Path("tests/public_golden/vnext_l3_credit_finance.json")


def _load_fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _build_evidence(fixture: dict) -> dict:
    lines = [
        {"content": line["content"], "bbox": line["bbox"], "confidence": line.get("confidence", 1.0)}
        for line in fixture["lines"]
    ]
    return extract_local_structure_evidence(
        lines,
        tokens=fixture["tokens"],
        page=4,
        page_width=fixture["page_width"],
        page_height=fixture["page_height"],
    )


def test_domain_access_reads_page_evidence_bundles():
    fixture = _load_fixture()
    evidence = _build_evidence(fixture)
    ds = domain_specific_with_page_bundles(
        page_evidence_bundle(
            4,
            local_structure_evidence={
                "page": 4,
                "structures": evidence.get("structures") or [],
            },
        ),
    )
    pages = local_structure_evidence_pages_from_domain_specific(ds)
    assert len(pages) == 1
    assert len(pages[0]["structures"]) >= 3
    assert "_scanned_local_structure_evidence" not in ds


def test_bundles_enrich_is_stable_across_repeated_calls():
    fixture = _load_fixture()
    evidence = _build_evidence(fixture)
    structures = evidence.get("structures") or []

    ds = domain_specific_with_page_bundles(
        page_evidence_bundle(4, local_structure_evidence={"page": 4, "structures": structures}),
    )
    pr = ParseResult(entities=DocumentEntities(document_type="credit_report", domain_specific=ds))
    out_first = enrich_credit_report_output({"data": {}}, parse_result=pr)
    out_second = enrich_credit_report_output({"data": {}}, parse_result=pr)

    def _values(data: dict) -> list[str]:
        accounts = data["data"]["credit_accounts"]
        return sorted(str(acc.get("management_institution", {}).get("value", "")) for acc in accounts)

    assert _values(out_first) == _values(out_second)
    assert len(out_first["data"]["credit_accounts"]) >= 3


def test_g4_golden_account2_fields_match_fixture():
    golden = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    fixture = _load_fixture()
    evidence = _build_evidence(fixture)
    out = extract_credit_accounts_from_local_structure_evidence(
        [{"page": 4, "structures": evidence.get("structures") or []}]
    )
    account = next(acc for acc in out["credit_accounts"] if "账户2" in str(acc.get("anchor", {}).get("value", "")))
    expected = golden["accounts_by_anchor_substring"]["账户2"]
    for field, want in expected.items():
        got = account[field]["value"] if isinstance(account.get(field), dict) else account.get(field)
        assert got == want, f"{field}: {got!r} != {want!r}"
