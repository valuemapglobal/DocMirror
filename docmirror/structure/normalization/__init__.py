"""UDTR page normalization primitives."""

from docmirror.structure.normalization.deskew import estimate_deskew_angle
from docmirror.structure.normalization.models import NormalizationCandidate, NormalizationTrace
from docmirror.structure.normalization.transform import (
    build_identity_trace,
    build_normalization_trace,
    invert_matrix,
    is_invertible_matrix,
    rotation_matrix,
)

__all__ = [
    "NormalizationCandidate",
    "NormalizationTrace",
    "build_identity_trace",
    "build_normalization_trace",
    "estimate_deskew_angle",
    "invert_matrix",
    "is_invertible_matrix",
    "rotation_matrix",
]
