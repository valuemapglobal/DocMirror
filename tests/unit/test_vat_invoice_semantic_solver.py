# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from docmirror.domains.vat_invoice import VATInvoiceSemanticSolver
from docmirror.models.entities.parse_result import DocumentEntities, PageContent, ParseResult, TextBlock, TextLevel
from docmirror.plugins.vat_invoice.community_plugin import VATInvoicePlugin

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
    assert any(item["id"] == "vat.amount_tax_total_equation" and item["status"] == "pass" for item in solution.invariant_results)


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
                    {"evidence_id": "ocr:p0:w000000", "text": "发票代码：", "bbox": [10, 10, 58, 24], "confidence": 0.98},
                    {"evidence_id": "ocr:p0:w000001", "text": "044002300411", "bbox": [60, 10, 160, 24], "confidence": 0.98},
                ]
            },
        ),
        TextBlock(content="发票号码：36538561", level=TextLevel.BODY, confidence=0.97, bbox=[180, 10, 310, 24]),
        TextBlock(content="开票日期：2024年05月27日", level=TextLevel.BODY, confidence=0.96, bbox=[320, 10, 500, 24]),
        TextBlock(content="称：卢子不加班（广州）咨询有限公司", level=TextLevel.BODY, confidence=0.95, bbox=[10, 52, 260, 70]),
        TextBlock(content="纳税人识别号：91440101190478645G", level=TextLevel.BODY, confidence=0.95, bbox=[10, 220, 280, 238]),
    ]
    parse_result = ParseResult(
        pages=[PageContent(page_number=1, texts=[*ocr_lines, TextBlock(content=VAT_OCR_TEXT, level=TextLevel.BODY)])],
        entities=DocumentEntities(document_type="vat_invoice"),
    )

    out = VATInvoicePlugin().extract_from_mirror(parse_result, VAT_OCR_TEXT)

    assert out["status"]["success"] is True
    assert out["data"]["fields"]["invoice_code"] == "044002300411"
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


def test_vat_invoice_solver_trims_same_line_ocr_noise() -> None:
    noisy = VAT_OCR_TEXT.replace(
        "称：卢子不加班（广州）咨询有限公司",
        "名 称：卢子不加班（广州）咨询有限公司 /708</-<638+*43149226+8+5<-",
    ).replace(
        "开户行及账号：中国银行股份有限公司广州东园支行、627575257856",
        "开户行及账号：中国银行股份有限公司广州东园支行、627575257856 区 84<-35803>330<83254-+<+///<",
        1,
    ).replace(
        "收款人：辰展",
        "收款人：辰展 复核：郑志伟 开票人：陈文玉 销售方：（） 发票专用章",
    )

    fields = VATInvoiceSemanticSolver().solve(full_text=noisy).canonical_model["fields"]

    assert fields["buyer_name"] == "卢子不加班(广州)咨询有限公司"
    assert fields["buyer_bank_account"] == "中国银行股份有限公司广州东园支行、627575257856"
    assert fields["payee"] == "辰展"
    assert fields["reviewer"] == "郑志伟"
    assert fields["issuer"] == "陈文玉"
