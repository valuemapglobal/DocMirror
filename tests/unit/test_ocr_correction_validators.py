from __future__ import annotations

from docmirror.ocr.correction import CorrectionContext, SafeOCRCorrector
from docmirror.ocr.correction.validator_registry import ValidatorRegistry
from docmirror.ocr.correction.validators import (
    repair_iban_if_unique,
    repair_uscc_if_unique,
    validate_amount_text,
    validate_date_text,
    validate_iban,
    validate_uscc,
)


def test_uscc_repairs_only_unique_checksum_candidate():
    valid = "91110000100000000R"
    observed = "9111O000100000000R"

    assert validate_uscc(valid)
    assert not validate_uscc(observed)
    assert repair_uscc_if_unique(observed) == valid


def test_uscc_is_repaired_in_labeled_text():
    decision = SafeOCRCorrector().correct(
        "统一社会信用代码:9111O000100000000R",
        CorrectionContext(role="text_line", domain="business_license"),
    )

    assert decision.output_text == "统一社会信用代码:91110000100000000R"
    assert decision.rule_id == "code.uscc_checksum"


def test_date_and_amount_validators_reject_impossible_values():
    assert validate_date_text("2026-07-17")
    assert not validate_date_text("2026-13-40")
    assert validate_amount_text("1,234.56")
    assert not validate_amount_text("1,23x.56")


def test_typed_amount_substitution_requires_valid_result():
    fixed = SafeOCRCorrector().correct("1,2S4.56", CorrectionContext(role="amount"))
    rejected = SafeOCRCorrector().correct("amount S", CorrectionContext(role="amount"))

    assert fixed.output_text == "1,254.56"
    assert rejected.output_text == "amount S"


def test_iban_checksum_and_unique_ocr_repair():
    valid = "GB82WEST12345698765432"
    observed = "GBB2WEST12345698765432"

    assert validate_iban(valid)
    assert not validate_iban(observed)
    assert repair_iban_if_unique(observed) == valid


def test_country_validator_registry_separates_checksum_and_format_only_rules():
    registry = ValidatorRegistry.default()

    iban = registry.evaluate("GBB2WEST12345698765432", field_type="iban")
    ein = registry.evaluate("12-3456789", field_type="ein", country="US")

    assert iban is not None and iban.repaired == "GB82WEST12345698765432"
    assert ein is not None and ein.valid and ein.format_only
