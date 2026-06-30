# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

from docmirror.ocr.local_structure import extract_local_structure_evidence
from docmirror.plugins.credit_report.account_structure import extract_credit_accounts_from_local_structure_evidence

_FIXTURE = Path("tests/fixtures/scanned/account_card_page4_full_layout.json")


def _load_fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _lines_from_fixture(fixture: dict) -> list[dict]:
    return [
        {"content": line["content"], "bbox": line["bbox"], "confidence": line.get("confidence", 1.0)}
        for line in fixture["lines"]
    ]


def test_full_page_snapshot_has_accounts_2_3_4():
    fixture = _load_fixture()
    assert len(fixture["lines"]) >= 40
    assert len(fixture["tokens"]) >= 60
    assert fixture["page"] == 4


def test_full_page_field_grid_extracts_three_accounts():
    fixture = _load_fixture()
    evidence = extract_local_structure_evidence(
        _lines_from_fixture(fixture),
        tokens=fixture["tokens"],
        page=4,
        page_width=fixture["page_width"],
        page_height=fixture["page_height"],
    )
    kinds = {s.get("structure_kind") for s in evidence.get("structures") or []}
    assert "field_grid" in kinds
    assert len(evidence.get("structures") or []) >= 3

    out = extract_credit_accounts_from_local_structure_evidence(
        [{"page": 4, "structures": evidence.get("structures") or []}]
    )
    accounts = out["credit_accounts"]
    assert len(accounts) >= 3
    anchors = [acc.get("anchor", {}).get("value", "") for acc in accounts]
    assert any("账户2" in anchor for anchor in anchors)
    assert any("账户3" in anchor for anchor in anchors)
    assert any("账户4" in anchor for anchor in anchors)


def test_full_page_account2_golden_fields():
    fixture = _load_fixture()
    evidence = extract_local_structure_evidence(
        _lines_from_fixture(fixture),
        tokens=fixture["tokens"],
        page=4,
        page_width=fixture["page_width"],
        page_height=fixture["page_height"],
    )
    out = extract_credit_accounts_from_local_structure_evidence(
        [{"page": 4, "structures": evidence.get("structures") or []}]
    )
    account = next(
        acc for acc in out["credit_accounts"] if "账户2" in str(acc.get("anchor", {}).get("value", ""))
    )
    assert account["management_institution"]["value"] == "重庆市蚂蚁商诚信息技术有限公司"
    assert "1000648287831" in account["account_identifier"]["value"]
    assert account["open_date"]["value"] == "2018.08.31"
    assert account["due_date"]["value"] == "2019.06.21"
    assert account["loan_amount"]["value"] == "72000"
    assert account["currency"]["value"] == "人民币"
    assert account["account_status"]["value"] == "结清"
    assert account["close_date"]["value"] == "2019.06.21"
    assert account["audit"]["field_count"] >= 8


def test_full_page_accounts_have_minimum_field_count():
    fixture = _load_fixture()
    evidence = extract_local_structure_evidence(
        _lines_from_fixture(fixture),
        tokens=fixture["tokens"],
        page=4,
        page_width=fixture["page_width"],
        page_height=fixture["page_height"],
    )
    out = extract_credit_accounts_from_local_structure_evidence(
        [{"page": 4, "structures": evidence.get("structures") or []}]
    )
    complete_accounts = [
        account
        for account in out["credit_accounts"]
        if account.get("audit", {}).get("projection_completeness") == "complete"
    ]
    assert len(complete_accounts) >= 3
    for account in complete_accounts[:3]:
        assert account["audit"]["field_count"] >= 6
        assert account["management_institution"]["bbox"]
        identifier = account.get("account_identifier")
        if isinstance(identifier, dict):
            refs = identifier.get("source_refs") or {}
            assert refs.get("cell_id") or refs.get("line_ids")
