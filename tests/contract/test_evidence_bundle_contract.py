# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.evidence.bundle import build_evidence_bundle
from docmirror.models.entities.parse_result import CellValue, PageContent, ParseResult, TableBlock, TableRow


def test_evidence_bundle_contains_quality_and_cell_sources():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                tables=[
                    TableBlock(
                        table_id="t1",
                        headers=["A"],
                        rows=[
                            TableRow(
                                cells=[
                                    CellValue(
                                        text="value",
                                        bbox=[1, 2, 3, 4],
                                        confidence=0.91,
                                        evidence_ids=["e1"],
                                    )
                                ]
                            )
                        ],
                    )
                ],
            )
        ]
    )

    bundle = build_evidence_bundle(result, task_id="task1", document_id="doc1")

    assert bundle["version"] == 2
    assert bundle["quality"]["audit_fidelity"]["source_refs"] in {"partial", "full"}
    assert bundle["field_evidence"][0]["value"] == "value"
    assert bundle["support"]["minimal_repro"]
