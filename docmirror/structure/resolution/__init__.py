# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Resolution package — document type classification and resolver framework.

Purpose: Collects evidence from keywords, headers, entities, plugins, and
visual cues to resolve the document type.

Main components: ``DocumentTypeResolver``, ``BaseResolver``.

Upstream: Pre-analysis, first-page content, plugin hints.

Downstream: ``scene.scene_resolver``, ``profile.resolver``.
"""

from docmirror.structure.resolution.base import ResolverDecision, ResolverScoreWeights

__all__ = [
    "ResolverDecision",
    "ResolverScoreWeights",
]
