from __future__ import annotations

from docmirror.ocr.correction import CorrectionContext, SafeOCRCorrector
from tests.benchmark.metrics import compute_cer


def test_targeted_correction_reduces_cer_without_hard_negative_regressions():
    corrector = SafeOCRCorrector()
    positives = [
        ("营业牧入", "营业收入", CorrectionContext(role="field_label", domain="financial_report")),
        ("资产负债牢", "资产负债率", CorrectionContext(role="field_label", domain="financial_report")),
        ("Micros0ft", "Microsoft", CorrectionContext(role="text_line")),
        ("Microsofl", "Microsoft", CorrectionContext(role="text_line")),
    ]
    negatives = [
        ("畜牧收入", CorrectionContext(role="text_line", domain="financial_report")),
        ("S123456", CorrectionContext(role="text_line")),
        ("Microsoft", CorrectionContext(role="text_line")),
        ("统一社会信用代码", CorrectionContext(role="field_label", domain="business_license")),
    ]

    raw_cer = sum(compute_cer(observed, expected) for observed, expected, _context in positives)
    fixed_cer = sum(
        compute_cer(corrector.correct(observed, context).output_text, expected)
        for observed, expected, context in positives
    )

    assert fixed_cer < raw_cer
    assert fixed_cer == 0.0
    for text, context in negatives:
        assert corrector.correct(text, context).output_text == text
