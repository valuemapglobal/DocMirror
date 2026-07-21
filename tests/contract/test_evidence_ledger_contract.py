# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for Evidence Ledger (GA 1.0 §8.4, OUT1-5).

Validates:
    1. Evidence ledger is built from ParseResult with fact_id / evidence_id stability.
    2. Page, text, table, and cell entries are created with correct fields.
    3. Ledger summary provides accurate coverage metrics.
    4. Evidence bundle v2 includes ledger and projection evidence.
"""

from docmirror.evidence.bundle import build_evidence_bundle
from docmirror.evidence.ledger import build_evidence_ledger, ledger_summary
from docmirror.models.entities.parse_result import CellValue, PageContent, ParseResult, TableBlock, TableRow, TextBlock


def test_evidence_ledger_builds_from_parse_result():
    """OUT1-5: Ledger collects page, text, table, and cell entries."""
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                tables=[
                    TableBlock(
                        table_id="t1",
                        headers=["Name", "Amount"],
                        rows=[
                            TableRow(
                                cells=[
                                    CellValue(text="Alice", bbox=[10, 10, 50, 20], confidence=0.95),
                                    CellValue(text="100.00", bbox=[60, 10, 100, 20], confidence=0.92),
                                ]
                            ),
                            TableRow(
                                cells=[
                                    CellValue(text="Bob", bbox=[10, 25, 50, 35], confidence=0.88),
                                    CellValue(text="200.00", bbox=[60, 25, 100, 35], confidence=0.97),
                                ]
                            ),
                        ],
                    )
                ],
            )
        ]
    )

    ledger = build_evidence_ledger(result)
    assert len(ledger) >= 5  # 1 page + 1 table + 4 cells

    page_entry = next((e for e in ledger if e["kind"] == "page"), None)
    assert page_entry is not None
    assert page_entry["fact_id"] == "page:1"
    assert page_entry["evidence_id"] == "ev:page:1"
    assert page_entry["review"] == "auto_accepted"

    table_entry = next((e for e in ledger if e["kind"] == "table"), None)
    assert table_entry is not None
    assert table_entry["fact_id"] == "table:p1:t0"
    assert table_entry["rows_count"] == 2

    cells = [e for e in ledger if e["kind"] == "cell"]
    assert len(cells) == 4
    cell_ids = sorted(c["fact_id"] for c in cells)
    assert cell_ids == ["cell:p1:t0:r0:c0", "cell:p1:t0:r0:c1", "cell:p1:t0:r1:c0", "cell:p1:t0:r1:c1"]

    for cell in cells:
        assert cell["evidence_id"].startswith("ev:cell:p1:t0:")
        assert cell["page"] == 1
        assert cell["confidence"] > 0

def test_evidence_ledger_summary_coverage():
    """OUT1-5: Ledger summary provides accurate coverage metrics."""
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                tables=[
                    TableBlock(
                        table_id="t1",
                        headers=["X"],
                        rows=[TableRow(cells=[CellValue(text="v", bbox=[1, 1, 2, 2], confidence=0.99)])],
                    )
                ],
            )
        ]
    )

    ledger = build_evidence_ledger(result)
    summary = ledger_summary(ledger)

    assert summary["total_entries"] > 0
    assert summary["by_kind"]["page"] == 1
    assert summary["by_kind"]["table"] == 1
    assert summary["by_kind"]["cell"] == 1

    assert summary["coverage"]["bbox"]["count"] >= 1
    assert summary["coverage"]["bbox"]["ratio"] > 0.0

    assert summary["confidence"]["mean"] > 0.0
    assert summary["review"]["auto_accepted"] >= 1

def test_evidence_bundle_v2_includes_ledger():
    """OUT1-5: Evidence bundle v2 includes the evidence ledger and projection evidence."""
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                tables=[
                    TableBlock(
                        table_id="t1",
                        headers=["Field"],
                        rows=[TableRow(cells=[CellValue(text="data", bbox=[0, 0, 10, 10], confidence=0.95, evidence_ids=["e1"])])],
                    )
                ],
            )
        ]
    )

    editions = {
        "community": {
            "plugin": {"name": "generic"},
            "data": {"fields": {"name": "test"}, "records": []},
            "metadata": {"support_level": "L0", "fallback_reason": None},
            "quality": {"confidence": 0.8},
        }
    }

    bundle = build_evidence_bundle(result, editions=editions, task_id="t1", document_id="d1")

    assert bundle["version"] == 2
    assert isinstance(bundle["ledger"], list)
    assert len(bundle["ledger"]) > 0
    assert isinstance(bundle["ledger_summary"], dict)
    assert bundle["ledger_summary"]["total_entries"] > 0

    assert isinstance(bundle["projection_evidence"], list)
    proj = bundle["projection_evidence"]
    assert any(p["target"] == "community.metadata" for p in proj)
    assert any(p["target"] == "community.data.fields.name" for p in proj)

    assert isinstance(bundle["unresolved"], list)
    assert isinstance(bundle["field_evidence"], list)
    fe = bundle["field_evidence"]
    assert any(f["field_path"] == "community.data.fields.name" for f in fe)

    assert "quality" in bundle
    assert "text_fidelity" in bundle["quality"]
    assert "support" in bundle
    assert "redaction_safe" in bundle["support"]

def test_evidence_ledger_deterministic():
    """OUT1-5: Same input produces same ledger (deterministic fact_ids and sort order)."""
    def make_result():
        return ParseResult(
            pages=[
                PageContent(
                    page_number=1,
                    tables=[
                        TableBlock(
                            table_id="t1",
                            headers=["A"],
                            rows=[TableRow(cells=[CellValue(text="x", confidence=0.8)])],
                        )
                    ],
                    texts=[TextBlock(content="hello", confidence=1.0)],
                )
            ]
        )

    ledger1 = build_evidence_ledger(make_result())
    ledger2 = build_evidence_ledger(make_result())

    assert len(ledger1) == len(ledger2)
    for e1, e2 in zip(ledger1, ledger2):
        assert e1["fact_id"] == e2["fact_id"]
        assert e1["evidence_id"] == e2["evidence_id"]
        assert e1["kind"] == e2["kind"]
