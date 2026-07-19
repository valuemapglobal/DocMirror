# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

from docmirror.models.entities.parse_result import CellValue, PageContent, TableBlock, TableRow
from docmirror.plugins.credit_report.report_profile import (
    detect_credit_report_content_mode,
    detect_credit_report_subtype,
    recover_credit_report_header_fields,
)


def _result(*pages: PageContent):
    return SimpleNamespace(pages=list(pages), full_text="")


def test_personal_brief_native_header_recovery_stops_at_adjacent_labels() -> None:
    result = _result(PageContent(page_number=1))
    text = """
    个人信用报告
    报告编号：2026071900012345678901
    报告时间：2026-07-19 09:08:07
    姓名：张三 证件类型：身份证 证件号码：11010519491231002X 已婚
    信贷记录 这部分包含您的信用卡、贷款和其他信贷记录。
    """

    fields = recover_credit_report_header_fields(result, text)

    assert detect_credit_report_subtype(result, text) == "personal_brief"
    assert detect_credit_report_content_mode(result) == "native_text"
    assert fields["subject_name"] == "张三"
    assert fields["id_type"] == "身份证"
    assert fields["id_number"] == "11010519491231002X"
    assert fields["report_time"] == "2026-07-19T09:08:07"
    assert fields["report_subtype"] == "personal_brief"
    assert fields["content_mode"] == "native_text"


def test_personal_detail_scan_profile_and_header_recovery() -> None:
    result = _result(PageContent(page_number=1, page_mode="scanned_ocr"))
    text = """
    个人信用报告（本人版）
    报告编号：2026071900012345678902
    被查询者姓名：李四 被查询者证件类型：身份证
    被查询者证件号码：11010519491231002X
    一、个人基本信息 三、信贷交易信息明细
    """

    fields = recover_credit_report_header_fields(result, text)

    assert detect_credit_report_subtype(result, text) == "personal_detail"
    assert detect_credit_report_content_mode(result) == "scanned_ocr"
    assert fields["subject_name"] == "李四"
    assert fields["id_number"] == "11010519491231002X"
    assert fields["report_subtype"] == "personal_detail"
    assert fields["content_mode"] == "scanned_ocr"


def test_personal_detail_recovers_identity_from_query_table_rows() -> None:
    table = TableBlock(
        rows=[
            TableRow(
                cells=[
                    CellValue(text="报告编号:2026071900012345678902"),
                    CellValue(text="报告时间:2026.07.1909:08:07"),
                ]
            ),
            TableRow(
                cells=[
                    CellValue(text="被查询者姓名"),
                    CellValue(text="被瓷询者证件类型"),
                    CellValue(text="被查询者证件号码 11010519491231002X"),
                    CellValue(text="查询机构"),
                ]
            ),
            TableRow(
                cells=[
                    CellValue(text="李四"),
                    CellValue(text="身份证"),
                    CellValue(text=""),
                    CellValue(text="本人"),
                ]
            ),
        ]
    )
    result = _result(PageContent(page_number=1, page_mode="scanned_ocr", tables=[table]))

    fields = recover_credit_report_header_fields(result, "个人信用报告（本人版） 信贷交易信息明细")

    assert fields["subject_name"] == "李四"
    assert fields["id_number"] == "11010519491231002X"
    assert fields["query_institution"] == "本人"
    assert fields["report_number"] == "2026071900012345678902"
    assert fields["report_time"] == "2026-07-19T09:08:07"


def test_enterprise_header_recovers_company_identifiers_and_no_number() -> None:
    result = _result(PageContent(page_number=1))
    text = """
    企业信用报告（自主查询版）
    NO.2026071900012345678903
    企业名称：示例科技股份有限公司
    中征码：3101150013301231
    统一社会信用代码：91310000MA1FL6NCX7
    查询机构：中国工商银行股份有限公司上海市分行
    报告时间：2026-07-19T10:40:34
    """

    fields = recover_credit_report_header_fields(result, text)

    assert detect_credit_report_subtype(result, text) == "enterprise"
    assert fields["subject_name"] == "示例科技股份有限公司"
    assert fields["company_name"] == "示例科技股份有限公司"
    assert fields["zhongzheng_code"] == "3101150013301231"
    assert fields["unified_social_credit_code"] == "91310000MA1FL6NCX7"
    assert fields["query_institution"] == "中国工商银行股份有限公司上海市分行"
    assert fields["report_number"] == "2026071900012345678903"
    assert fields["report_time"] == "2026-07-19T10:40:34"
    assert fields["report_subtype"] == "enterprise"


def test_enterprise_detection_needs_title_or_both_identifiers() -> None:
    result = _result(PageContent(page_number=1))

    assert detect_credit_report_subtype(result, "担保人证件类型：中征码") == "unknown"
    assert (
        detect_credit_report_subtype(
            result, "企业名称 示例公司 中征码 1234567890123456 统一社会信用代码 91310000MA1FL6NCX7"
        )
        == "enterprise"
    )
