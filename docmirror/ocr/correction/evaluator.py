# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Offline golden-corpus evaluation for deterministic OCR correction."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from docmirror.ocr.correction.engine import SafeOCRCorrector
from docmirror.ocr.correction.models import CorrectionContext


@dataclass(frozen=True)
class EvaluationSample:
    original: str
    expected: str
    context: CorrectionContext = field(default_factory=CorrectionContext)
    sample_id: str = ""


@dataclass(frozen=True)
class EvaluationCase:
    sample_id: str
    original: str
    expected: str
    actual: str
    action: str
    passed: bool
    category: str
    rule_id: str | None = None
    language: str | None = None
    country: str | None = None
    domain: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "original": self.original,
            "expected": self.expected,
            "actual": self.actual,
            "action": self.action,
            "passed": self.passed,
            "category": self.category,
            **({"rule_id": self.rule_id} if self.rule_id else {}),
            **({"language": self.language} if self.language else {}),
            **({"country": self.country} if self.country else {}),
            **({"domain": self.domain} if self.domain else {}),
        }


@dataclass(frozen=True)
class EvaluationReport:
    total: int
    passed: int
    corrected: int
    missed: int
    false_positive: int
    wrong_correction: int
    cases: tuple[EvaluationCase, ...]

    @property
    def precision(self) -> float:
        denominator = self.corrected + self.false_positive + self.wrong_correction
        return self.corrected / denominator if denominator else 1.0

    @property
    def recall(self) -> float:
        denominator = self.corrected + self.missed + self.wrong_correction
        return self.corrected / denominator if denominator else 1.0

    def to_dict(self, *, include_cases: bool = True) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "corrected": self.corrected,
            "missed": self.missed,
            "false_positive": self.false_positive,
            "wrong_correction": self.wrong_correction,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "by_language": _case_breakdown(self.cases, "language"),
            "by_country": _case_breakdown(self.cases, "country"),
            "by_domain": _case_breakdown(self.cases, "domain"),
            "by_rule": _case_breakdown(self.cases, "rule_id"),
            **({"cases": [case.to_dict() for case in self.cases]} if include_cases else {}),
        }


def evaluate_samples(
    samples: Iterable[EvaluationSample], corrector: SafeOCRCorrector | None = None
) -> EvaluationReport:
    corrector = corrector or SafeOCRCorrector()
    cases: list[EvaluationCase] = []
    for index, sample in enumerate(samples, start=1):
        decision = corrector.correct(sample.original, sample.context)
        actual = decision.output_text
        expected_change = sample.expected != sample.original
        actual_change = actual != sample.original
        if actual == sample.expected:
            category = "corrected" if expected_change else "true_negative"
        elif not expected_change and actual_change:
            category = "false_positive"
        elif expected_change and not actual_change:
            category = "missed"
        else:
            category = "wrong_correction"
        cases.append(
            EvaluationCase(
                sample_id=sample.sample_id or f"sample:{index:06d}",
                original=sample.original,
                expected=sample.expected,
                actual=actual,
                action=decision.action,
                passed=actual == sample.expected,
                category=category,
                rule_id=decision.rule_id,
                language=decision.language or sample.context.language,
                country=decision.country or sample.context.country,
                domain=decision.domain or sample.context.domain,
            )
        )
    return EvaluationReport(
        total=len(cases),
        passed=sum(case.passed for case in cases),
        corrected=sum(case.category == "corrected" for case in cases),
        missed=sum(case.category == "missed" for case in cases),
        false_positive=sum(case.category == "false_positive" for case in cases),
        wrong_correction=sum(case.category == "wrong_correction" for case in cases),
        cases=tuple(cases),
    )


def load_evaluation_samples(path: str | Path) -> list[EvaluationSample]:
    source = Path(path).expanduser().resolve()
    files = sorted(source.rglob("*")) if source.is_dir() else [source]
    samples: list[EvaluationSample] = []
    for file_path in files:
        if file_path.suffix.lower() not in {".json", ".jsonl", ".yaml", ".yml"}:
            continue
        for item in _load_records(file_path):
            if not isinstance(item, dict):
                continue
            context_data = item.get("context") if isinstance(item.get("context"), dict) else {}
            context = CorrectionContext(
                role=str(context_data.get("role") or item.get("role") or "unknown"),
                domain=str(context_data.get("domain") or item.get("domain") or "") or None,
                mode="safe",
                language=str(context_data.get("language") or item.get("language") or "") or None,
                country=str(context_data.get("country") or item.get("country") or "") or None,
                locale=str(context_data.get("locale") or item.get("locale") or "") or None,
                pack_ids=tuple(str(value) for value in context_data.get("pack_ids") or item.get("pack_ids") or []),
                metadata=dict(context_data.get("metadata") or {}),
            )
            original = str(item.get("original") or "")
            expected = str(item.get("expected", item.get("corrected", original)))
            samples.append(EvaluationSample(original, expected, context, str(item.get("id") or "")))
    return samples


def _load_records(path: Path) -> list[Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    value = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    if isinstance(value, dict):
        value = value.get("samples", [value])
    return list(value or []) if isinstance(value, list) else []


def _case_breakdown(cases: tuple[EvaluationCase, ...], field_name: str) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for case in cases:
        key = str(getattr(case, field_name) or "unknown")
        bucket = out.setdefault(key, {"total": 0, "passed": 0, "failed": 0})
        bucket["total"] += 1
        bucket["passed" if case.passed else "failed"] += 1
    return dict(sorted(out.items()))


__all__ = [
    "EvaluationCase",
    "EvaluationReport",
    "EvaluationSample",
    "evaluate_samples",
    "load_evaluation_samples",
]
