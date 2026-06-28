# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Detection middleware package — scene, language, and institution identification.

Re-exports ``InstitutionDetector`` and ``LanguageDetector`` for pipeline
profiles that run early in the MEP stack to populate ``ParseResult.entities``
before extraction and validation stages.
"""

from .institution_detector import InstitutionDetector
from .language_detector import LanguageDetector

__all__ = ["LanguageDetector", "InstitutionDetector"]
