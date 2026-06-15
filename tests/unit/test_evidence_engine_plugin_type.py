# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""M9: EvidenceEngine plugin_document_type hint for PEC routing."""

from __future__ import annotations

from unittest.mock import patch

from docmirror.core.scene.evidence_engine import EvidenceEngine
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult


def test_evidence_engine_sets_plugin_document_type_alias():
    result = ParseResult(
        full_text="银行对账单 sample",
        entities=DocumentEntities(document_type="unknown"),
    )
    with patch.object(
        EvidenceEngine,
        "_fuse_evidence",
        return_value=("bank_reconciliation", 0.95, []),
    ):
        out = EvidenceEngine().process(result)
    ds = out.entities.domain_specific or {}
    assert out.entities.document_type == "bank_reconciliation"
    assert ds.get("plugin_document_type") == "bank_statement"
