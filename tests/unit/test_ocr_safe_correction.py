from __future__ import annotations

from docmirror.input.extraction.extractor import _correct_ocr_blocks, _ocr_word_confidence
from docmirror.models.entities.domain import Block, TextSpan
from docmirror.ocr.correction import CorrectionContext, SafeOCRCorrector
from docmirror.ocr.correction.lexicon import CorrectionLexicon
from docmirror.ocr.scanned.universal import _correct_table_result


def test_corrects_controlled_english_terms_without_touching_codes():
    corrector = SafeOCRCorrector()

    assert corrector.correct("Micros0ft Corporation", CorrectionContext(role="text_line")).output_text == (
        "Microsoft Corporation"
    )
    assert corrector.correct("Microsofl Corporation", CorrectionContext(role="text_line")).output_text == (
        "Microsoft Corporation"
    )
    assert corrector.correct("S123456", CorrectionContext(role="text_line")).output_text == "S123456"


def test_chinese_finance_correction_is_context_scoped():
    corrector = SafeOCRCorrector()

    fixed = corrector.correct(
        "营业牧入",
        CorrectionContext(role="field_label", domain="financial_report"),
    )
    negative = corrector.correct(
        "畜牧收入",
        CorrectionContext(role="text_line", domain="financial_report"),
    )

    assert fixed.output_text == "营业收入"
    assert fixed.rule_id == "finance.operating_revenue"
    assert negative.action == "unchanged"
    assert negative.output_text == "畜牧收入"


def test_labeled_line_uses_field_context_without_touching_value():
    decision = SafeOCRCorrector().correct(
        "注册资木:1000万元",
        CorrectionContext(role="text_line", domain="business_license"),
    )

    assert decision.output_text == "注册资本:1000万元"


def test_suggest_mode_records_candidate_without_mutating_output():
    decision = SafeOCRCorrector().correct(
        "Microsofl Corporation",
        CorrectionContext(role="text_line", mode="suggest"),
    )

    assert decision.action == "suggested"
    assert decision.corrected == "Microsoft Corporation"
    assert decision.output_text == "Microsofl Corporation"


def test_ambiguous_dictionary_candidate_is_not_applied():
    lexicon = CorrectionLexicon(
        {
            "thresholds": {"max_weighted_distance": 1.0, "min_candidate_margin": 0.5},
            "lexicons": {
                "ambiguous": {
                    "roles": ["text_line"],
                    "terms": ["testa", "testb"],
                }
            },
        }
    )

    decision = SafeOCRCorrector(lexicon).correct("testc", CorrectionContext(role="text_line"))
    assert decision.action == "unchanged"
    assert decision.output_text == "testc"


def test_block_correction_preserves_geometry_confidence_and_evidence():
    block = Block(
        block_id="ocr:p0001:0001",
        block_type="text",
        spans=(TextSpan(text="Microsofl Corporation", bbox=(1.0, 2.0, 30.0, 12.0)),),
        bbox=(1.0, 2.0, 30.0, 12.0),
        raw_content="Microsofl Corporation",
        attrs={"ocr_source": "rapidocr", "confidence": 0.63},
        evidence_ids=("ocr:p0001:0001",),
    )

    corrected = _correct_ocr_blocks([block], mode="safe")[0]

    assert corrected.raw_content == "Microsoft Corporation"
    assert corrected.spans[0].text == "Microsoft Corporation"
    assert corrected.bbox == block.bbox
    assert corrected.evidence_ids == block.evidence_ids
    assert corrected.attrs["confidence"] == 0.63
    assert corrected.attrs["ocr_original_text"] == "Microsofl Corporation"
    assert corrected.attrs["ocr_correction"]["action"] == "applied"


def test_word_confidence_supports_legacy_and_word_box_tuples():
    assert _ocr_word_confidence((0, 0, 1, 1, "x", 0.61)) == 0.61
    assert _ocr_word_confidence((0, 0, 1, 1, "x", 0, 0, 0, 0.72)) == 0.72


def test_correction_is_idempotent():
    corrector = SafeOCRCorrector()
    first = corrector.correct("Micros0ft", CorrectionContext(role="text_line")).output_text
    second = corrector.correct(first, CorrectionContext(role="text_line")).output_text
    assert first == "Microsoft"
    assert second == first


def test_universal_table_correction_uses_locale_pack_and_cell_audit():
    result = _correct_table_result(
        {"table": [["指标", "金额"], ["应收账款周转牢", "1.2"]]},
        page_idx=0,
        mode="safe",
        domain="financial_report",
        language=None,
        country=None,
        locale="zh-CN",
        pack_ids=(),
    )

    assert result["table"][1][0] == "应收账款周转率"
    assert result["ocr_corrections"]["events"][0]["target"] == {
        "kind": "table_cell",
        "page": 1,
        "table": 0,
        "row": 1,
        "column": 0,
    }
