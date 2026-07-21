# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Private-fixture coverage for the three public credit-report subtypes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfReader

from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.input.entry.options import normalize_parse_policy
from docmirror.models.schemas.registry import validate_projection_payload
from docmirror.plugins.credit_report.business_records import extract_native_credit_business
from docmirror.server.output_builder import build_community_output
from tests._community_reading import assert_community_reading_view
from tests._credit_report_golden import sha256_file

pytestmark = [pytest.mark.integration, pytest.mark.slow, pytest.mark.tier_slow]

_FIXTURE_DIR = Path("tests/fixtures-private/credit_report")
_GOLDEN_MANIFEST = _FIXTURE_DIR / "golden" / "manifest.json"


def _candidate_case(path: Path) -> dict:
    manifest = json.loads(_GOLDEN_MANIFEST.read_text(encoding="utf-8"))
    source_hash = sha256_file(path)
    return next(case for case in manifest["cases"] if case["source_sha256"] == source_hash)


def _private_cases(pattern: str, prefix: str) -> list[pytest.ParameterSet]:
    paths = sorted(_FIXTURE_DIR.glob(pattern))
    if not paths:
        return [pytest.param(Path("__missing__"), id=f"{prefix}-missing", marks=pytest.mark.skip)]
    return [pytest.param(path, id=f"{prefix}-{index}") for index, path in enumerate(paths, start=1)]


def _extract(path: Path, *, max_pages: int | None) -> dict:
    result = asyncio.run(
        perceive_document(
            path,
            PerceiveOptions(policy=normalize_parse_policy(enhance_mode="standard", max_pages=max_pages)),
        )
    )
    output = build_community_output(result, result.full_text or "", file_path=str(path))
    assert output is not None
    return output


@pytest.mark.parametrize("fixture", _private_cases("*_个人简版征信报告.pdf", "personal-brief"))
def test_personal_brief_native_report_profile(fixture: Path) -> None:
    output = _extract(fixture, max_pages=8)
    data = output["data"]
    fields = data["fields"]

    assert output["plugin"]["name"] == "credit_report"
    assert validate_projection_payload("community", output).valid is True
    assert fields["report_subtype"] == "personal_brief"
    assert fields["content_mode"] == "native_text"
    assert fields["subject_name"]
    assert len(fields["id_number"]) in {15, 18}
    assert fields["report_number"]
    assert fields["report_time"]
    assert data["sections"]
    assert_community_reading_view(data)
    assert len(data["credit_accounts"]) == 87
    assert len({item["account_id"] for item in data["credit_accounts"]}) == 87
    assert all(item["normalized"]["account_id"] for item in data["credit_accounts"])
    assert len(data["credit_lines"]) == 6
    assert len(data["overdue_records"]) == 3
    assert len(data["inquiry_records"]) == 108
    assert data["credit_summary"]["institution_inquiry_count"] == 104
    assert data["credit_summary"]["personal_inquiry_count"] == 4
    assert data["records"] == []
    assert data["credit_extraction_audit"]["document_complete"] is True
    assert data["credit_extraction_audit"]["status"] == "pass"
    assert output["validation"]["domain_contract"]["status"] == "pass"
    assert output["quality"]["readiness"] == "ready"


@pytest.mark.parametrize("fixture", _private_cases("*_企业征信*.pdf", "enterprise"))
def test_enterprise_native_report_profile(fixture: Path) -> None:
    output = _extract(fixture, max_pages=None)
    data = output["data"]
    fields = data["fields"]

    assert output["plugin"]["name"] == "credit_report"
    assert validate_projection_payload("community", output).valid is True
    assert fields["report_subtype"] == "enterprise"
    assert fields["content_mode"] == "native_text"
    assert fields["subject_name"] == fields["company_name"]
    assert len(fields["unified_social_credit_code"]) == 18
    assert fields["zhongzheng_code"]
    assert fields["report_number"]
    assert fields["report_time"]
    assert data["sections"]
    assert_community_reading_view(data)
    expected_counts = _candidate_case(fixture)["expected"]["counts"]
    assert len(data["credit_accounts"]) == expected_counts["credit_accounts"]
    assert all(item["normalized"]["account_id"] for item in data["credit_accounts"])
    assert len(data["credit_lines"]) == 2
    assert len(data["public_records"]) == expected_counts["public_records"]
    assert data["credit_summary"]["first_credit_year"] >= 2000
    assert data["credit_summary"]["credit_institution_count"] > 0
    assert data["credit_summary"]["credit_balance"] >= 0
    assert data["records"] == []
    assert data["credit_extraction_audit"]["document_complete"] is True
    assert data["credit_extraction_audit"]["status"] == "pass"
    assert output["validation"]["domain_contract"]["status"] == "pass"
    assert output["quality"]["readiness"] == "ready"


@pytest.mark.parametrize("fixture", _private_cases("*_企业征信*.pdf", "enterprise-accounts"))
def test_enterprise_full_native_text_account_history(fixture: Path) -> None:
    # The final account histories live in a 70+ page appendix. Exercise the
    # domain parser directly here; a full Community envelope would duplicate
    # the generic post-extract cost without adding account-parser coverage.
    text = "\n".join(page.extract_text() or "" for page in PdfReader(fixture).pages)

    business = extract_native_credit_business(
        SimpleNamespace(pages=[]),
        text,
        report_subtype="enterprise",
        content_mode="native_text",
    )

    accounts = business["credit_accounts"]
    assert len(accounts) >= 190
    assert len({item["account_id"] for item in accounts}) == len(accounts)
    assert all(item["management_institution"] for item in accounts)
    assert all(item["business_type"] for item in accounts)
    public_records = business["public_records"]
    expected_counts = _candidate_case(fixture)["expected"]["counts"]
    for collection, expected_count in expected_counts.items():
        assert len(business.get(collection) or []) == expected_count
    assert len({item["public_record_id"] for item in public_records}) == len(public_records)
    assert all(item["authority"] and len(item["authority"]) <= 60 for item in public_records)
    assert all("许可部门" not in item["authority"] for item in public_records)
    assert all(item["content"] for item in public_records)


@pytest.mark.parametrize("fixture", _private_cases("*_个人详版征信报告.pdf", "personal-detail"))
def test_personal_detail_scanned_report_profile(fixture: Path) -> None:
    # Two source pages are sufficient to cover the rotated query table and the
    # first report sections without turning this into a full 28-page OCR test.
    output = _extract(fixture, max_pages=2)
    data = output["data"]
    fields = data["fields"]

    assert output["plugin"]["name"] == "credit_report"
    assert validate_projection_payload("community", output).valid is True
    assert fields["report_subtype"] == "personal_detail"
    assert fields["content_mode"] == "scanned_ocr"
    assert fields["subject_name"]
    assert len(fields["id_number"]) in {15, 18}
    assert fields["report_number"]
    assert fields["report_time"]
    assert data["sections"]
    assert_community_reading_view(data)
    assert output["validation"]["domain_contract"]["status"] == "partial"
    assert "credit_extraction_audit:status" in output["validation"]["domain_contract"]["missing_collections"]
    assert output["quality"]["readiness"] == "review"
    assert "precision:document_truncated" in output["status"]["warnings"]
