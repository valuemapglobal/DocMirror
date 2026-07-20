from __future__ import annotations

import json

from click.testing import CliRunner

from docmirror.cli.main import main
from docmirror.ocr.correction import CorrectionContext, SafeOCRCorrector
from docmirror.ocr.correction.config_schema import validate_pack_data
from docmirror.ocr.correction.evaluator import EvaluationSample, evaluate_samples
from docmirror.ocr.correction.language import detect_script, resolve_language_hint
from docmirror.ocr.correction.packs import CorrectionPackRegistry
from docmirror.ocr.correction.tokenizers import TokenizerRegistry


def test_builtin_locale_pack_is_selected_and_audited():
    decision = SafeOCRCorrector().correct(
        "应收账款周转牢",
        CorrectionContext(role="field_label", domain="financial_report", locale="zh-CN"),
    )

    assert decision.output_text == "应收账款周转率"
    assert decision.pack_id == "zh-CN.financial-statement"
    assert decision.language == "zh"
    assert decision.country == "CN"
    assert "zh-CN.financial-statement" in decision.selected_pack_ids


def test_language_pack_does_not_leak_into_another_locale():
    decision = SafeOCRCorrector().correct(
        "应收账款周转牢",
        CorrectionContext(role="field_label", domain="financial_report", locale="ja-JP"),
    )

    assert decision.output_text == "应收账款周转牢"


def test_script_detection_and_tokenizer_registry_are_dependency_free():
    assert detect_script("請求書番号")[0] == "Han"
    assert resolve_language_hint("請求書かな").language == "ja"
    tokens = TokenizerRegistry.default().resolve(language="ar").tokenize("رقم الفاتورة 123")
    assert [token.text for token in tokens] == ["رقم", "الفاتورة", "123"]


def test_pack_validation_rejects_conflicts_and_cycles():
    issues = validate_pack_data(
        {
            "pack_id": "broken",
            "version": 1,
            "exact_rules": [
                {"id": "one", "observed": "A", "canonical": "B"},
                {"id": "two", "observed": "B", "canonical": "A"},
            ],
        }
    )

    assert {issue.code for issue in issues} == {"rule.cycle"}


def test_custom_opt_in_pack_requires_explicit_id(tmp_path):
    path = tmp_path / "customer.yaml"
    path.write_text(
        """
pack_id: customer.finance
version: 1
priority: 1000
opt_in: true
exact_rules:
  - id: customer.term
    observed: 私有错词
    canonical: 私有正词
    roles: [field_label]
""".strip(),
        encoding="utf-8",
    )
    registry = CorrectionPackRegistry.from_paths([path], include_builtin=False)
    corrector = SafeOCRCorrector(pack_registry=registry)

    disabled = corrector.correct("私有错词", CorrectionContext(role="field_label"))
    enabled = corrector.correct(
        "私有错词",
        CorrectionContext(role="field_label", pack_ids=("customer.finance",)),
    )

    assert disabled.output_text == "私有错词"
    assert enabled.output_text == "私有正词"


def test_higher_priority_pack_overrides_same_scoped_rule(tmp_path):
    low = tmp_path / "low.yaml"
    high = tmp_path / "high.yaml"
    low.write_text(
        """
pack_id: project.base
version: 1
priority: 10
exact_rules:
  - id: base.term
    observed: 待修词
    canonical: 基础词
    roles: [field_label]
""".strip(),
        encoding="utf-8",
    )
    high.write_text(
        """
pack_id: customer.override
version: 2
priority: 1000
exact_rules:
  - id: customer.term
    observed: 待修词
    canonical: 客户词
    roles: [field_label]
""".strip(),
        encoding="utf-8",
    )
    registry = CorrectionPackRegistry.from_paths([low, high], include_builtin=False)

    decision = SafeOCRCorrector(pack_registry=registry).correct("待修词", CorrectionContext(role="field_label"))

    assert not registry.issues
    assert decision.output_text == "客户词"
    assert decision.pack_id == "customer.override"
    assert decision.pack_version == 2


def test_same_priority_cross_pack_conflict_is_rejected(tmp_path):
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    template = """
pack_id: {pack_id}
version: 1
priority: 100
exact_rules:
  - id: {rule_id}
    observed: 冲突词
    canonical: {canonical}
    roles: [field_label]
"""
    first.write_text(
        template.format(pack_id="project.first", rule_id="first.term", canonical="结果一").strip(),
        encoding="utf-8",
    )
    second.write_text(
        template.format(pack_id="project.second", rule_id="second.term", canonical="结果二").strip(),
        encoding="utf-8",
    )

    registry = CorrectionPackRegistry.from_paths([first, second], include_builtin=False)

    assert any(issue.code == "rule.cross_pack_conflict" for issue in registry.issues)
    assert [pack.pack_id for pack in registry.packs] == ["project.first"]


def test_offline_evaluator_reports_false_positives_and_misses():
    report = evaluate_samples(
        [
            EvaluationSample("Micros0ft", "Microsoft", CorrectionContext(role="text_line"), "positive"),
            EvaluationSample("S123456", "S123456", CorrectionContext(role="text_line"), "negative"),
        ]
    )

    assert report.total == 2
    assert report.passed == 2
    assert report.precision == 1.0
    assert report.recall == 1.0


def test_ocr_correction_cli_validate_explain_and_evaluate(tmp_path):
    runner = CliRunner()
    validate_result = runner.invoke(main, ["ocr", "check"])
    explain_result = runner.invoke(
        main,
        [
            "ocr",
            "explain",
            "应收账款周转牢",
            "--role",
            "field_label",
            "--domain",
            "financial_report",
            "--locale",
            "zh-CN",
        ],
    )
    samples = tmp_path / "samples.json"
    samples.write_text(
        json.dumps(
            [
                {
                    "id": "one",
                    "original": "Micros0ft",
                    "expected": "Microsoft",
                    "context": {"role": "text_line"},
                }
            ]
        ),
        encoding="utf-8",
    )
    evaluate_result = runner.invoke(main, ["ocr", "eval", str(samples), "--fail-on-regression"])

    assert validate_result.exit_code == 0
    assert "finance.receivables_turnover_rate" in explain_result.output
    assert evaluate_result.exit_code == 0
    assert '"passed": 1' in evaluate_result.output
