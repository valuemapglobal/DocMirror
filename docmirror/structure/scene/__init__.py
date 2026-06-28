# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Scene package — document scene classification and evidence rules.

Purpose: Determines high-level document scene (bank statement, invoice, etc.)
from rules and evidence for profile selection.

Main components: ``resolve_document_scene``, ``EvidenceEngine``.

Upstream: Pre-analysis, resolver output, full text.

Downstream: ``profile.resolver``, ``classification`` middleware.
"""

from docmirror.structure.scene.evidence_engine import Evidence, EvidenceEngine
from docmirror.structure.scene.rules import ClassificationRule, ClassificationRules, RuleManager
from docmirror.structure.scene.scene_resolver import resolve_document_scene, scene_to_layout_profile_id

__all__ = [
    "ClassificationRule",
    "ClassificationRules",
    "Evidence",
    "EvidenceEngine",
    "RuleManager",
    "resolve_document_scene",
    "scene_to_layout_profile_id",
]
