# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

from docmirror.evidence.repair import RepairDecision, RepairRequest
from docmirror.ocr.repair import LocalOCRRepairEngine


def test_repair_request_requires_page_and_bbox_to_render() -> None:
    request = RepairRequest(
        request_id="repair:1",
        domain="bank_statement",
        kind="missing_ledger_row_local_ocr",
        expected_schema=("date", "amount"),
    )

    assert not request.can_render
    assert request.to_dict()["can_render"] is False


def test_local_ocr_repair_engine_fuses_consensus_candidates() -> None:
    np = pytest.importorskip("numpy")
    image = np.full((100, 200, 3), 255, dtype=np.uint8)
    request = RepairRequest(
        request_id="repair:bank:1",
        domain="bank_statement",
        kind="missing_ledger_row_local_ocr",
        page_number=1,
        bbox=(10.0, 10.0, 80.0, 30.0),
    )

    def recognizer_a(_image):
        return [{"source": "engine_a", "text": "20220701 支出 27.79 61.81", "confidence": 0.82}]

    def recognizer_b(_image):
        return [{"source": "engine_b", "text": "20220701支出27.7961.81", "confidence": 0.78}]

    engine = LocalOCRRepairEngine(recognizers=[recognizer_a, recognizer_b])
    candidates = engine.repair_from_image(
        request,
        image,
        page_width=100.0,
        page_height=100.0,
        max_variants=2,
    )

    assert candidates
    assert candidates[0].request_id == "repair:bank:1"
    assert candidates[0].confidence >= 0.78
    assert candidates[0].source == "ocr_repair_fusion"


def test_repair_decision_does_not_auto_adopt_without_domain_gate() -> None:
    decision = RepairDecision(
        request_id="repair:bank:1",
        status="needs_review",
        action="manual_review",
        reasons=("evidence_only_candidate",),
    )

    assert not decision.adopted
    assert decision.to_dict()["action"] == "manual_review"
