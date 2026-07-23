# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Detection middleware package — generic scene and language identification.

Re-exports ``LanguageDetector`` for pipeline profiles that run early in the MEP
stack. Domain institution identification belongs to the owning plugin.
"""

from .language_detector import LanguageDetector

__all__ = ["LanguageDetector"]
