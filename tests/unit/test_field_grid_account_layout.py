# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

from docmirror.structure.ocr.local_structure import extract_local_structure_evidence
from docmirror.plugins.credit_report.account_structure import extract_credit_accounts_from_local_structure_evidence

_FIXTURE = Path("tests/fixtures/scanned/account_card_page4_layout.json")


def _load_fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def test_field_grid_builds_on_realistic_account_layout():
    fixture = _load_fixture()
    evidence = extract_local_structure_evidence(
        fixture["lines"],
        tokens=fixture["tokens"],
        page=4,
        page_width=fixture["page_width"],
        page_height=fixture["page_height"],
    )
    assert evidence["structures"]
    structure = evidence["structures"][0]
    assert structure["structure_kind"] == "field_grid"
    assert len(structure.get("cells") or []) >= 6
    labels = {cell.get("label_text") for cell in structure.get("cells") or []}
    assert "管理机构" in labels
    assert "账户标识" in labels


def test_field_grid_account_mapper_improves_key_fields():
    fixture = _load_fixture()
    evidence = extract_local_structure_evidence(
        fixture["lines"],
        tokens=fixture["tokens"],
        page=4,
        page_width=fixture["page_width"],
        page_height=fixture["page_height"],
    )
    out = extract_credit_accounts_from_local_structure_evidence(
        [{"page": 4, "structures": evidence.get("structures") or []}]
    )
    assert out["credit_accounts"]
    account = out["credit_accounts"][0]
    assert account["management_institution"]["value"] == "重庆市蚂蚁商诚信息技术有限公司"
    assert "1000648287831" in account["account_identifier"]["value"]
    assert account["currency"]["value"] == "人民币"
    assert account["open_date"]["value"] == "2018.08.31"
    assert account["due_date"]["value"] == "2019.06.21"
    assert account["loan_amount"]["value"] == "72000"
    assert account["account_status"]["value"] == "结清"
    assert account["close_date"]["value"] == "2019.06.21"
    assert account["audit"]["field_source"] == "local_structure_field_grid"
    assert "第4页，共56页" not in str(account.get("open_date", {}))


def test_field_grid_disabled_falls_back_to_label_value_graph(monkeypatch):
    import docmirror.structure.ocr.local_structure.build as build_mod

    monkeypatch.setattr(build_mod, "ENABLE_FIELD_GRID", False)
    fixture = _load_fixture()
    evidence = extract_local_structure_evidence(
        fixture["lines"],
        tokens=fixture["tokens"],
        page=4,
        page_width=fixture["page_width"],
        page_height=fixture["page_height"],
    )
    kinds = {s.get("structure_kind") for s in evidence.get("structures") or []}
    assert "label_value_graph" in kinds
