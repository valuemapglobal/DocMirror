from pathlib import Path

from docmirror.structure.ocr.local_structure import extract_local_structure_evidence
from docmirror.structure.ocr.page_canvas.evidence_bundles import domain_specific_with_page_bundles, page_evidence_bundle
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult
from docmirror.plugins._base.kv_community_enrich import enrich_credit_report_output
from docmirror.plugins.credit_report.account_structure import extract_credit_accounts_from_local_structure_evidence


def _credit_account_lines():
    return [
        {"content": "账户2", "bbox": [20, 10, 70, 24], "confidence": 1.0},
        {"content": "管理机构 账户标识 开立日期", "bbox": [20, 40, 320, 54], "confidence": 1.0},
        {
            "content": "重庆市蚂蚁商诚信 蚂蚁借呗合并20180831J1010111000648287831 2018.08.31",
            "bbox": [20, 60, 520, 74],
            "confidence": 1.0,
        },
        {"content": "账户币种 到期日期 借款金额", "bbox": [20, 90, 320, 104], "confidence": 1.0},
        {"content": "人民币 2019.06.21 72,000", "bbox": [20, 110, 320, 124], "confidence": 1.0},
        {"content": "业务种类 担保方式 账户状态 关闭日期", "bbox": [20, 140, 420, 154], "confidence": 1.0},
        {"content": "其他个人消费贷款 信用/免担保 结清 2019.06.21", "bbox": [20, 160, 420, 174], "confidence": 1.0},
        {"content": "账户3", "bbox": [20, 210, 70, 224], "confidence": 1.0},
        {"content": "管理机构账户标识开立日期", "bbox": [20, 240, 320, 254], "confidence": 1.0},
        {"content": "重庆市蚂蚁商诚信 ABC123 2020.01.02", "bbox": [20, 260, 420, 274], "confidence": 1.0},
        {"content": "账户币种到期日期借款金额", "bbox": [20, 290, 320, 304], "confidence": 1.0},
        {"content": "人民币 2021.01.02 10000", "bbox": [20, 310, 320, 324], "confidence": 1.0},
    ]


def test_local_structure_splits_scanned_account_blocks_and_multicolumn_values():
    evidence = extract_local_structure_evidence(_credit_account_lines(), page=4, page_width=600, page_height=800)

    assert len(evidence["candidates"]) == 2
    assert len(evidence["structures"]) == 2
    first = evidence["structures"][0]
    labels = [node["text"] for node in first["nodes"] if node["role"] == "label"]
    values = [node["text"] for node in first["nodes"] if node["role"] == "value"]

    assert labels[:3] == ["管理机构", "账户标识", "开立日期"]
    assert "72,000" in values
    assert "信用/免担保" in values
    assert all(edge["reason_codes"] == ["paired_label_value_rows", "x_band_alignment"] for edge in first["edges"])


def test_credit_plugin_maps_local_structure_to_accounts_with_bbox_refs():
    evidence = extract_local_structure_evidence(_credit_account_lines(), page=4, page_width=600, page_height=800)

    out = extract_credit_accounts_from_local_structure_evidence([{"page": 4, "structures": evidence["structures"]}])

    assert len(out["credit_accounts"]) == 2
    account = out["credit_accounts"][0]
    assert account["management_institution"]["value"] == "重庆市蚂蚁商诚信息技术有限公司"
    assert account["management_institution"]["raw"] == "重庆市蚂蚁商诚信"
    assert account["account_identifier"]["value"].startswith("蚂蚁借呗合并")
    assert account["open_date"]["value"] == "2018.08.31"
    assert account["currency"]["value"] == "人民币"
    assert account["loan_amount"]["value"] == "72000"
    assert account["account_status"]["value"] == "结清"
    assert account["account_identifier"]["bbox"]
    assert account["account_identifier"]["source_refs"]["line_ids"]


def test_local_structure_continuation_chain_is_preserved_in_account_field():
    lines = [
        {"content": "账户2", "bbox": [20, 10, 70, 24], "confidence": 1.0},
        {"content": "管理机构 账户标识 开立日期", "bbox": [20, 40, 320, 54], "confidence": 1.0},
        {
            "content": "重庆市蚂蚁商诚信 蚂蚁借呗合并20180831J1010111000648287831 2018.08.31",
            "bbox": [20, 60, 520, 74],
            "confidence": 1.0,
        },
        {"content": "J1020222000648287831", "bbox": [120, 76, 310, 90], "confidence": 1.0},
        {"content": "账户币种 到期日期 借款金额", "bbox": [20, 110, 320, 124], "confidence": 1.0},
        {"content": "人民币 2019.06.21 72,000", "bbox": [20, 130, 320, 144], "confidence": 1.0},
    ]
    evidence = extract_local_structure_evidence(lines, page=4, page_width=600, page_height=800)
    out = extract_credit_accounts_from_local_structure_evidence([{"page": 4, "structures": evidence["structures"]}])

    account = out["credit_accounts"][0]
    assert "J1020222000648287831" in account["account_identifier"]["value"]
    assert len(account["account_identifier"]["source_refs"]["line_ids"]) == 2
    assert account["account_identifier"]["audit"]["continuation_node_ids"]
    continuation_edges = [
        edge for edge in evidence["structures"][0]["edges"]
        if edge["relation"] == "continuation"
    ]
    assert continuation_edges


def test_region_crop_ocr_is_audit_only(monkeypatch):
    from docmirror.structure.ocr.local_structure import repair

    class FakeImage:
        shape = (800, 600, 3)

    class FakeRecognition:
        text = "修复候选"
        confidence = 0.88
        source = "region_crop_ocr"
        raw_text = "修复候选"
        audit = {"region": (1, 2, 3, 4)}

        def to_dict(self):
            return {
                "text": self.text,
                "confidence": self.confidence,
                "source": self.source,
                "raw_text": self.raw_text,
                "audit": self.audit,
            }

    def fake_recognize(*args, **kwargs):
        return FakeRecognition()

    monkeypatch.setattr(repair, "recognize_structure_region_from_image", fake_recognize)
    evidence = extract_local_structure_evidence(
        _credit_account_lines(),
        page=4,
        page_width=600,
        page_height=800,
        page_image=FakeImage(),
        enable_region_ocr=True,
    )

    first_value = next(node for node in evidence["structures"][0]["nodes"] if node["role"] == "value")
    assert first_value["text"] == "重庆市蚂蚁商诚信"
    assert first_value["audit"]["region_crop_ocr"]["text"] == "修复候选"
    assert evidence["structures"][0]["audit"]["region_crop_ocr"]["mode"] == "audit_only"


def test_credit_enrichment_consumes_generic_scanned_local_structure_evidence():
    evidence = extract_local_structure_evidence(_credit_account_lines(), page=4, page_width=600, page_height=800)
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=domain_specific_with_page_bundles(
                page_evidence_bundle(
                    4,
                    local_structure_evidence={"page": 4, "structures": evidence["structures"]},
                ),
            ),
        )
    )

    enriched = enrich_credit_report_output({"data": {}, "document": {}}, parse_result=pr)

    assert len(enriched["data"]["credit_accounts"]) == 2
    assert pr.entities.domain_specific["credit_accounts"][0]["account_status"]["value"] == "结清"
    assert pr.entities.domain_specific["_local_structures"]


def test_credit_enrichment_is_idempotent_for_local_structures():
    evidence = extract_local_structure_evidence(_credit_account_lines(), page=4, page_width=600, page_height=800)
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=domain_specific_with_page_bundles(
                page_evidence_bundle(
                    4,
                    local_structure_evidence={"page": 4, "structures": evidence["structures"]},
                ),
            ),
        )
    )

    enrich_credit_report_output({"data": {}, "document": {}}, parse_result=pr)
    enrich_credit_report_output({"data": {}, "document": {}}, parse_result=pr)

    structure_ids = [item["structure_id"] for item in pr.entities.domain_specific["_local_structures"]]
    assert len(structure_ids) == len(set(structure_ids))


def test_forensic_api_exports_scanned_local_structure_evidence_only():
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific=domain_specific_with_page_bundles(
                page_evidence_bundle(
                    4,
                    local_structure_evidence={
                        "page": 4,
                        "lines": [{"content": "账户", "bbox": [1, 2, 3, 4]}],
                        "tokens": [{"token_id": "t1", "text": "账", "bbox": [1, 2, 2, 4]}],
                        "structures": [{"structure_id": "ls1"}],
                    },
                ),
            ),
        )
    )

    standard = pr.to_mirror_json_vnext(mirror_level="standard")
    forensic = pr.to_mirror_json_vnext(mirror_level="forensic")

    assert "scanned_local_structure_evidence" not in standard
    forensic_doc = forensic
    assert forensic_doc["scanned_ocr_pages"][0]["page"] == 4
    evidence = forensic_doc["scanned_local_structure_evidence"][0]
    assert evidence["page"] == 4
    assert evidence["ocr_page_ref"] == forensic_doc["scanned_ocr_pages"][0]["ocr_page_id"]
    assert "lines" not in evidence
    assert "tokens" not in evidence


def test_core_local_structure_does_not_export_credit_specific_mappers():
    core_files = Path("docmirror/core/ocr/local_structure").glob("*.py")
    source = "\n".join(path.read_text(encoding="utf-8") for path in core_files)

    assert "repayment" not in source.lower()
    assert "extract_credit" not in source
