# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Universal resolver layer — evidence scoring and conflict resolution (L4)."""

from docmirror.core.resolution.base import ResolverDecision, ResolverScoreWeights

__all__ = [
    "ResolverDecision",
    "ResolverScoreWeights",
]
