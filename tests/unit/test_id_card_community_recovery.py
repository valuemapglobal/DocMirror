# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from docmirror.layout.scene.evidence_engine import EvidenceEngine
from docmirror.models.entities.parse_result import (
    DocumentEntities,
    PageContent,
    ParseResult,
    TextBlock,
    TextLevel,
)
from docmirror.output.community_bundle import project_community_bundle
from docmirror.plugins._base.generic_community_adapter import build_generic_community_output
from docmirror.plugins._runtime.runner import run_plugin_extract_sync

ID_CARD_OCR_TEXT = """姓名 李四

性别 女 民族 汉

出生 1949 年 12 月 31 日

住址 北京市朝阳区建国路

88号2单元101室

<div><img src="portrait.jpg" /></div>

11010519491231002X"""

ID_CARD_DERIVED_TABLE_TEXT = """姓名\t李四
性别\t女
民族\t汉
出生\t1949 年 12 月 31 日
住址\t北京市朝阳区建国路
公民身份号码\t11010519491231002X"""

LONG_ADDRESS_OCR_TEXT = """姓名测试用户

性别女 民族汉

出生1949年12月31日

住址 示例市示例区示例中路

3000号10栋2单元33层2号

公民身份号码 11010519491231002X"""

LONG_ADDRESS_DERIVED_TABLE_TEXT = """姓名\t测试用户
性别\t女
民族\t汉
出生\t1949年12月31日
住址\t示例市示例区示例中路
公民身份号码\t11010519491231002X"""


def _result(text: str = ID_CARD_OCR_TEXT, *, document_type: str = "generic") -> ParseResult:
    return ParseResult(
        pages=[
            PageContent(
                page_number=1,
                page_mode="scanned_ocr",
                texts=[TextBlock(content=text, level=TextLevel.BODY)],
            )
        ],
        raw_text=text,
        entities=DocumentEntities(document_type=document_type),
    )


def test_id_card_fixed_frame_is_classification_evidence() -> None:
    result = _result()

    EvidenceEngine().process(result)

    assert result.entities.document_type == "id_card"


def test_id_card_frame_rejects_invalid_checksum() -> None:
    invalid = ID_CARD_OCR_TEXT.replace("11010519491231002X", "110105194912310020")

    evidence = EvidenceEngine()._id_card_frame_evidence(invalid)

    assert evidence == []


def test_forced_id_card_recovers_space_delimited_fields_and_multiline_address() -> None:
    output = build_generic_community_output(_result(document_type="id_card"), "id_card", ID_CARD_OCR_TEXT)

    assert output["data"]["fields"] == {
        "name": "李四",
        "gender": "女",
        "ethnicity": "汉",
        "birth_date": "1949-12-31",
        "address": "北京市朝阳区建国路88号2单元101室",
        "id_number": "11010519491231002X",
    }
    assert "no_fields_extracted" not in output["status"]["warnings"]


def test_id_card_source_text_is_not_overwritten_by_truncated_derived_table() -> None:
    result = _result(document_type="id_card")
    polluted_full_text = f"{ID_CARD_OCR_TEXT}\n\n{ID_CARD_DERIVED_TABLE_TEXT}"

    output = build_generic_community_output(result, "id_card", polluted_full_text)

    assert output["data"]["fields"]["address"] == "北京市朝阳区建国路88号2单元101室"
    assert "precision:id_card_address_conflict" not in output["status"]["warnings"]


def test_id_card_repeated_short_address_cannot_replace_complete_address() -> None:
    repeated_source = f"{ID_CARD_OCR_TEXT}\n\n{ID_CARD_DERIVED_TABLE_TEXT}"
    result = _result(repeated_source, document_type="id_card")

    output = build_generic_community_output(result, "id_card", repeated_source)

    assert output["data"]["fields"]["address"] == "北京市朝阳区建国路88号2单元101室"
    assert "precision:id_card_address_conflict" not in output["status"]["warnings"]


def test_long_address_is_complete_in_community_json_without_fake_dataset() -> None:
    result = _result(LONG_ADDRESS_OCR_TEXT, document_type="id_card")
    polluted_full_text = f"{LONG_ADDRESS_OCR_TEXT}\n\n{LONG_ADDRESS_DERIVED_TABLE_TEXT}"

    output = run_plugin_extract_sync(result, edition="community", full_text=polluted_full_text)

    assert output is not None
    bundle = project_community_bundle(result, file_id="001", document_id="doc_id_card_long_address")
    payload = bundle.json_payload()
    items = {item["key"]: item for item in payload["sections"][0]["items"]}
    expected = "示例市示例区示例中路3000号10栋2单元33层2号"

    assert items["address"]["value"] == expected
    assert items["address"]["raw"] == expected
    assert bundle.render_dataset_csvs() == {}


def test_id_card_facts_reach_community_bundle_without_becoming_dataset_rows() -> None:
    result = _result()
    EvidenceEngine().process(result)
    output = run_plugin_extract_sync(result, edition="community", full_text=result.full_text)

    assert output is not None
    bundle = project_community_bundle(result, file_id="001", document_id="doc_id_card")
    payload = bundle.json_payload()
    items = {item["key"]: item for item in payload["sections"][0]["items"]}

    assert payload["document"]["type"] == "id_card"
    assert set(items) == {"name", "gender", "ethnicity", "birth_date", "address", "id_number"}
    assert items["birth_date"]["value"] == "1949-12-31"
    assert items["birth_date"]["raw"] == "1949 年 12 月 31 日"
    assert items["address"]["value"] == "北京市朝阳区建国路88号2单元101室"
    assert "NO_FIELDS_EXTRACTED" not in {warning["code"] for warning in payload["warnings"]}
    assert payload["warnings"] == [
        {
            "code": "COMMUNITY_GENERIC_FALLBACK",
            "level": "info",
            "message": "community_generic_fallback",
        }
    ]
    assert payload["datasets"] == []
    assert bundle.render_dataset_csvs() == {}
    assert bundle.render_audit_csv().count("\n") == 1
