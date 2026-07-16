# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public deterministic OCR safe-correction API."""

from docmirror.ocr.correction.engine import SafeOCRCorrector, normalize_ocr_unicode
from docmirror.ocr.correction.models import CorrectionContext, CorrectionDecision, CorrectionMode
from docmirror.ocr.correction.packs import CorrectionPack, CorrectionPackRegistry
from docmirror.ocr.correction.validator_registry import ValidatorRegistry
from docmirror.ocr.correction.validators import (
    repair_iban_if_unique,
    repair_uscc_if_unique,
    validate_iban,
    validate_uscc,
)

__all__ = [
    "CorrectionContext",
    "CorrectionDecision",
    "CorrectionMode",
    "CorrectionPack",
    "CorrectionPackRegistry",
    "SafeOCRCorrector",
    "normalize_ocr_unicode",
    "repair_iban_if_unique",
    "repair_uscc_if_unique",
    "validate_iban",
    "validate_uscc",
    "ValidatorRegistry",
]
