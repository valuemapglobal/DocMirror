# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Human-readable reports for OCR correction evaluation."""

from __future__ import annotations

from docmirror.ocr.correction.evaluator import EvaluationReport


def evaluation_markdown(report: EvaluationReport) -> str:
    lines = [
        "# OCR correction evaluation",
        "",
        f"- Total: {report.total}",
        f"- Passed: {report.passed}",
        f"- Precision: {report.precision:.2%}",
        f"- Recall: {report.recall:.2%}",
        f"- Missed: {report.missed}",
        f"- False positives: {report.false_positive}",
        f"- Wrong corrections: {report.wrong_correction}",
    ]
    failures = [case for case in report.cases if not case.passed]
    if failures:
        lines.extend(["", "## Failures", ""])
        for case in failures:
            lines.append(
                f"- `{case.sample_id}` {case.category}: `{case.original}` → `{case.actual}` (expected `{case.expected}`)"
            )
    return "\n".join(lines) + "\n"


__all__ = ["evaluation_markdown"]
