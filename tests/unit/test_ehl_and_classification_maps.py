# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""EHL annex + classification rules map tests."""

from __future__ import annotations

import os

from docmirror.configs.classification.rules_loader import (
    categories_with_scene_maps,
    get_maps_to_scenes,
)
from docmirror.core.scene.evidence_engine import Evidence
from docmirror.models.ehl import attach_classification_annex, evidence_items_to_hypotheses
from docmirror.models.entities.parse_result import ParseResult


class TestClassificationRulesMaps:
    def test_identity_personal_maps_to_scenes(self):
        scenes = get_maps_to_scenes("identity_personal")
        assert "id_card" in scenes
        assert "passport" in scenes

    def test_categories_with_scene_maps_non_empty(self):
        mapped = categories_with_scene_maps()
        assert "identity_personal" in mapped
        assert "identity_enterprise" in mapped


class TestEhlAnnex:
    def test_evidence_to_hypotheses(self):
        ev = Evidence("keyword", "wechat_payment", 0.9, 1, "matched 微信")
        hyps = evidence_items_to_hypotheses([ev], selected_category="wechat_payment")
        assert len(hyps) == 1
        assert hyps[0].selected is True
        assert hyps[0].kind == "document_type"

    def test_attach_classification_annex(self):
        os.environ["DOCMIRROR_DEBUG"] = "1"
        try:
            pr = ParseResult()
            ev = Evidence("keyword", "bank_statement", 0.8, 1, "银行流水")
            attach_classification_annex(pr, [ev], selected_category="bank_statement")
            assert pr.annex is not None
            assert len(pr.annex.hypotheses) == 1
            assert pr.annex.evidence_summary is not None
            assert pr.annex.evidence_summary.total_spans == 1
        finally:
            os.environ.pop("DOCMIRROR_DEBUG", None)
