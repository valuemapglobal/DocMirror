# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from types import SimpleNamespace

from docmirror.domains.vat_invoice import VATInvoiceSemanticSolver
from docmirror.domains.vat_invoice.solver import (
    _recover_header_fields_from_mirror,
    _recover_line_items_from_mirror,
)
from docmirror.models.entities.parse_result import DocumentEntities, PageContent, ParseResult, TextBlock, TextLevel
from docmirror.plugins.vat_invoice.community_plugin import VATInvoicePlugin, _canonicalize_vat_fields

VAT_OCR_TEXT = """
发票代码：044002300411
广东增值税电子普通发票
发票号码：36538561
开票日期：2024年05月27日
校验码：84088347412981965726
机器编号：661911894496
称：卢子不加班（广州）咨询有限公司
纳税人识别号：91440101MA9Y8EBY4P
地址、电话：广州市天河区岑村圣堂大街工业区38号二层A区785、13825079485
开户行及账号：中国银行股份有限公司广州东园支行、627575257856
税率
税霸
单价
金额
数量
货物或应税劳务、服务名称
9.17
101.83
项
*运输服务*地铁客运服务费
¥9.17
¥101.83
合计
(小写）¥111.00
价税合计（大写）
壹佰壹拾壹圆整
称：广州地铁集团有限公司
纳税人识别号：91440101190478645G
地址、电话：广州市海珠区新港东路1238号万胜广场A塔、02086673366
开户行及账号：广州市建行大德路支行、4001420301050130412
开票人：陈文玉
复核：郑志伟
收款人：辰展
""".strip()

VAT_ENGLISH_TEXT = """
Value-Added Tax Invoice
Invoice Code: 3100212130
Invoice Number: 87654321
Issue Date: 2025-03-15
Seller: Shanghai Dongfang Technology Co., Ltd.
Seller Tax ID: 91310000MA1FL6NCX7
Buyer: Beijing Innovation Enterprise Co., Ltd.
Buyer Tax ID: 91110108MA01ABCD1
Total Amount (excl. tax): CNY 85,000.00
VAT Rate: 13%
VAT Amount: CNY 11,050.00
Total Amount (incl. tax): CNY 96,050.00
Item Description Qty Unit Price Amount
1 Software Development Service 1 50,000.00 50,000.00
2 Technical Consulting 2 17,500.00 35,000.00
Payee: Zhang Wei Reviewer: Li Ming Drawer: Wang Fang
""".strip()


def test_vat_invoice_solver_extracts_core_fields_and_amount_equation() -> None:
    solution = VATInvoiceSemanticSolver().solve(full_text=VAT_OCR_TEXT)

    assert solution.success
    fields = solution.canonical_model["fields"]
    assert fields["invoice_code"] == "044002300411"
    assert fields["invoice_number"] == "36538561"
    assert fields["issue_date"] == "2024-05-27"
    assert fields["buyer_name"] == "卢子不加班(广州)咨询有限公司"
    assert fields["seller_name"] == "广州地铁集团有限公司"
    assert fields["amount_without_tax"] == "101.83"
    assert fields["tax_amount"] == "9.17"
    assert fields["total_amount"] == "111.00"
    assert any(
        item["id"] == "vat.amount_tax_total_equation" and item["status"] == "pass"
        for item in solution.invariant_results
    )


def test_vat_invoice_solver_supports_english_word_split_layout() -> None:
    word_split = "\n\n".join(VAT_ENGLISH_TEXT.replace("\n", " ").split(" "))
    solution = VATInvoiceSemanticSolver().solve(full_text=word_split)

    assert solution.success
    fields = solution.canonical_model["fields"]
    assert fields["invoice_code"] == "3100212130"
    assert fields["invoice_number"] == "87654321"
    assert fields["buyer_name"] == "Beijing Innovation Enterprise Co., Ltd."
    assert fields["seller_name"] == "Shanghai Dongfang Technology Co., Ltd."
    assert fields["amount_without_tax"] == "85000.00"
    assert fields["tax_amount"] == "11050.00"
    assert fields["total_amount"] == "96050.00"
    assert len(solution.canonical_model["line_items"]) == 2
    assert solution.canonical_model["line_items"][0]["description"] == "Software Development Service"


def test_vat_invoice_plugin_uses_semantic_solver_before_generic_kv() -> None:
    ocr_lines = [
        TextBlock(
            content="发票代码：044002300411",
            level=TextLevel.BODY,
            confidence=0.98,
            bbox=[10, 10, 160, 24],
            evidence_ids=["ocr:p0:w000000", "ocr:p0:w000001"],
            slm_entities={
                "ocr_tokens": [
                    {
                        "evidence_id": "ocr:p0:w000000",
                        "text": "发票代码：",
                        "bbox": [10, 10, 58, 24],
                        "confidence": 0.98,
                    },
                    {
                        "evidence_id": "ocr:p0:w000001",
                        "text": "044002300411",
                        "bbox": [60, 10, 160, 24],
                        "confidence": 0.98,
                    },
                ]
            },
        ),
        TextBlock(content="发票号码：36538561", level=TextLevel.BODY, confidence=0.97, bbox=[180, 10, 310, 24]),
        TextBlock(content="开票日期：2024年05月27日", level=TextLevel.BODY, confidence=0.96, bbox=[320, 10, 500, 24]),
        TextBlock(
            content="称：卢子不加班（广州）咨询有限公司", level=TextLevel.BODY, confidence=0.95, bbox=[10, 52, 260, 70]
        ),
        TextBlock(
            content="纳税人识别号：91440101190478645G", level=TextLevel.BODY, confidence=0.95, bbox=[10, 220, 280, 238]
        ),
    ]
    parse_result = ParseResult(
        pages=[PageContent(page_number=1, texts=[*ocr_lines, TextBlock(content=VAT_OCR_TEXT, level=TextLevel.BODY)])],
        entities=DocumentEntities(document_type="vat_invoice"),
    )

    out = VATInvoicePlugin().extract_from_mirror(parse_result, VAT_OCR_TEXT)

    assert out["status"]["success"] is True
    assert out["data"]["fields"]["invoice_code"] == "044002300411"
    assert out["data"]["fields"]["invoice_date"] == "2024-05-27"
    assert "issue_date" not in out["data"]["fields"]
    assert out["data"]["fields"]["seller_tax_id"] == "91440101190478645G"
    assert out["data"]["line_items"][0]["item_name"] == "*运输服务*地铁客运服务费"
    assert out["metadata"]["solver"]["name"] == "vat_invoice_text_solver_p0"
    assert out["metadata"]["field_provenance_status"]["source"] == "ocr_text_blocks"
    assert out["metadata"]["field_provenance_status"]["matched_field_count"] >= 4
    assert out["metadata"]["field_provenance_status"]["field_level_bbox"] is False
    assert out["metadata"]["field_provenance"]["invoice_code"]["bbox"] == [60.0, 10.0, 160.0, 24.0]
    assert out["metadata"]["field_provenance"]["invoice_code"]["line_bbox"] == [10.0, 10.0, 160.0, 24.0]
    assert out["metadata"]["field_provenance"]["invoice_code"]["evidence_ids"] == ["ocr:p0:w000001"]
    assert out["metadata"]["field_provenance"]["invoice_code"]["token_match"] == "token_subset"
    assert out["metadata"]["field_provenance"]["buyer_name"]["page"] == 1
    assert out["metadata"]["field_provenance"]["buyer_name"]["text"] == "称：卢子不加班（广州）咨询有限公司"


def test_vat_public_date_alias_does_not_silently_hide_conflicts() -> None:
    fields, warnings = _canonicalize_vat_fields({"issue_date": "2024-05-27", "invoice_date": "2024-05-28"})

    assert fields["invoice_date"] == "2024-05-28"
    assert "issue_date" not in fields
    assert warnings == ["vat_invoice_date_conflict"]


def test_vat_solver_recovers_split_header_values_from_mirror_atoms() -> None:
    atoms = [
        {"page_id": "page:0001", "text": "发票代码:", "bbox": [430.0, 10.0, 475.0, 20.0]},
        {"page_id": "page:0001", "text": "044002300411", "bbox": [475.0, 10.0, 525.0, 20.0]},
        {"page_id": "page:0001", "text": "发票号码:", "bbox": [430.0, 30.0, 475.0, 40.0]},
        {"page_id": "page:0001", "text": "12345678", "bbox": [475.0, 30.0, 510.0, 40.0]},
        {"page_id": "page:0001", "text": "开票日期:", "bbox": [430.0, 50.0, 475.0, 60.0]},
        {"page_id": "page:0001", "text": "2026", "bbox": [477.0, 50.0, 499.0, 60.0]},
        {"page_id": "page:0001", "text": "07", "bbox": [509.0, 50.0, 520.0, 60.0]},
        {"page_id": "page:0001", "text": "18", "bbox": [531.0, 50.0, 542.0, 60.0]},
        {"page_id": "page:0001", "text": "¥101.83", "bbox": [438.0, 84.0, 478.0, 94.0]},
        {"page_id": "page:0001", "text": "¥9.17", "bbox": [557.0, 84.0, 590.0, 94.0]},
        {"page_id": "page:0001", "text": "（小写）", "bbox": [448.0, 100.0, 475.0, 110.0]},
        {"page_id": "page:0001", "text": "¥111.00", "bbox": [474.0, 100.0, 514.0, 110.0]},
    ]
    parse_result = SimpleNamespace(
        full_text="",
        _runtime_mirror_cache={"evidence": {"text_atoms": atoms}},
    )
    text_without_header_values = "\n".join(
        line for line in VAT_OCR_TEXT.splitlines() if not line.startswith(("发票代码", "发票号码", "开票日期"))
    ).replace("(小写）¥111.00", "(小写）¥119.49")

    fields = (
        VATInvoiceSemanticSolver()
        .solve(
            full_text=text_without_header_values,
            parse_result=parse_result,
        )
        .canonical_model["fields"]
    )
    recovered = _recover_header_fields_from_mirror(parse_result)

    assert fields["invoice_code"] == "044002300411"
    assert fields["invoice_number"] == "12345678"
    assert fields["issue_date"] == "2026-07-18"
    assert fields["amount_without_tax"] == "101.83"
    assert fields["tax_amount"] == "9.17"
    assert fields["total_amount"] == "111.00"
    assert recovered["amount_without_tax"] == "101.83"
    assert recovered["tax_amount"] == "9.17"
    assert any(
        item["id"] == "vat.amount_tax_total_equation" and item["status"] == "pass"
        for item in VATInvoiceSemanticSolver()
        .solve(full_text=text_without_header_values, parse_result=parse_result)
        .invariant_results
    )


def test_vat_invoice_solver_recovers_every_positioned_line_item_column() -> None:
    atoms = [
        {"page_id": "page:0001", "text": "货物或应税劳务、服务名称", "bbox": [10.0, 30.0, 150.0, 40.0]},
        {"page_id": "page:0001", "text": "规格型号", "bbox": [160.0, 30.0, 200.0, 40.0]},
        {"page_id": "page:0001", "text": "单位", "bbox": [210.0, 30.0, 230.0, 40.0]},
        {"page_id": "page:0001", "text": "数", "bbox": [260.0, 30.0, 270.0, 40.0]},
        {"page_id": "page:0001", "text": "量", "bbox": [280.0, 30.0, 290.0, 40.0]},
        {"page_id": "page:0001", "text": "单", "bbox": [330.0, 30.0, 340.0, 40.0]},
        {"page_id": "page:0001", "text": "价", "bbox": [350.0, 30.0, 360.0, 40.0]},
        {"page_id": "page:0001", "text": "金", "bbox": [410.0, 30.0, 420.0, 40.0]},
        {"page_id": "page:0001", "text": "额", "bbox": [430.0, 30.0, 440.0, 40.0]},
        {"page_id": "page:0001", "text": "税率", "bbox": [490.0, 30.0, 510.0, 40.0]},
        {"page_id": "page:0001", "text": "税", "bbox": [540.0, 30.0, 550.0, 40.0]},
        {"page_id": "page:0001", "text": "额", "bbox": [560.0, 30.0, 570.0, 40.0]},
        {"page_id": "page:0001", "text": "*运输服务*客运服务费", "bbox": [10.0, 50.0, 145.0, 60.0]},
        {"page_id": "page:0001", "text": "标准", "bbox": [160.0, 50.0, 195.0, 60.0]},
        {"page_id": "page:0001", "text": "项", "bbox": [210.0, 50.0, 225.0, 60.0]},
        {"page_id": "page:0001", "text": "1", "bbox": [270.0, 50.0, 278.0, 60.0]},
        {"page_id": "page:0001", "text": "101.83", "bbox": [335.0, 50.0, 375.0, 60.0]},
        {"page_id": "page:0001", "text": "101.83", "bbox": [410.0, 50.0, 450.0, 60.0]},
        {"page_id": "page:0001", "text": "9%", "bbox": [490.0, 50.0, 510.0, 60.0]},
        {"page_id": "page:0001", "text": "9.17", "bbox": [545.0, 50.0, 575.0, 60.0]},
        {"page_id": "page:0001", "text": "合", "bbox": [20.0, 80.0, 30.0, 90.0]},
    ]
    parse_result = SimpleNamespace(_runtime_mirror_cache={"evidence": {"text_atoms": atoms}})

    assert _recover_line_items_from_mirror(parse_result) == [
        {
            "item_name": "*运输服务*客运服务费",
            "specification": "标准",
            "unit": "项",
            "quantity": "1",
            "unit_price": "101.83",
            "amount": "101.83",
            "tax_rate": "9%",
            "tax_amount": "9.17",
            "total_amount": "111.00",
        }
    ]


def test_vat_invoice_solver_trims_same_line_ocr_noise() -> None:
    noisy = (
        VAT_OCR_TEXT.replace(
            "称：卢子不加班（广州）咨询有限公司",
            "名 称：卢子不加班（广州）咨询有限公司 /708</-<638+*43149226+8+5<-",
        )
        .replace(
            "开户行及账号：中国银行股份有限公司广州东园支行、627575257856",
            "开户行及账号：中国银行股份有限公司广州东园支行、627575257856 区 84<-35803>330<83254-+<+///<",
            1,
        )
        .replace(
            "收款人：辰展",
            "收款人：辰展 复核：郑志伟 开票人：陈文玉 销售方：（） 发票专用章",
        )
    )

    fields = VATInvoiceSemanticSolver().solve(full_text=noisy).canonical_model["fields"]

    assert fields["buyer_name"] == "卢子不加班(广州)咨询有限公司"
    assert fields["buyer_bank_account"] == "中国银行股份有限公司广州东园支行、627575257856"
    assert fields["payee"] == "辰展"
    assert fields["reviewer"] == "郑志伟"
    assert fields["issuer"] == "陈文玉"
