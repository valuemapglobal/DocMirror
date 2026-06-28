"""Universal evidence verification layer."""

from docmirror.geometry.verification.builder import build_verification_report
from docmirror.geometry.verification.crops import attach_unit_crop_ocr_candidates, attach_verification_crop_assets
from docmirror.geometry.verification.models import (
    VerificationCandidate,
    VerificationClaim,
    VerificationReport,
    VerificationRule,
    VerifiedUnit,
)
from docmirror.geometry.verification.quality_gates import build_verification_quality_gates
from docmirror.geometry.verification.rule_packs import (
    FunctionVerificationRulePack,
    VerificationRulePackRegistry,
    default_verification_rule_pack_registry,
)

__all__ = [
    "FunctionVerificationRulePack",
    "VerificationCandidate",
    "VerificationClaim",
    "VerificationReport",
    "VerificationRule",
    "VerificationRulePackRegistry",
    "VerifiedUnit",
    "attach_unit_crop_ocr_candidates",
    "attach_verification_crop_assets",
    "build_verification_quality_gates",
    "build_verification_report",
    "default_verification_rule_pack_registry",
]
