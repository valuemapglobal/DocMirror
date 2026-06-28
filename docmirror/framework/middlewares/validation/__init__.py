# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Validation middleware package — fidelity scoring and mutation analysis.

Re-exports the mirror fidelity ``Validator`` and ``MutationAnalyzer`` for
post-extraction quality measurement and iterative layout-profile tuning
suggestions.
"""

from .mutation_analyzer import MutationAnalyzer
from .validator import Validator

__all__ = ["Validator", "MutationAnalyzer"]
