# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OCR correction pack maintenance commands."""

from __future__ import annotations

import json
from pathlib import Path

import click

from docmirror.ocr.correction import CorrectionContext, SafeOCRCorrector
from docmirror.ocr.correction.evaluator import evaluate_samples, load_evaluation_samples
from docmirror.ocr.correction.feedback import feedback_from_events, write_feedback_jsonl
from docmirror.ocr.correction.packs import CorrectionPackRegistry


@click.group("ocr-correction")
def ocr_correction() -> None:
    """Maintain deterministic OCR correction packs and golden samples."""


@ocr_correction.command("validate")
@click.argument("paths", nargs=-1, type=click.Path(path_type=Path, exists=True))
def validate_packs(paths: tuple[Path, ...]) -> None:
    """Validate built-in packs or one or more custom pack paths."""
    registry = (
        CorrectionPackRegistry.from_paths(paths, include_builtin=False) if paths else CorrectionPackRegistry.default()
    )
    for issue in registry.issues:
        click.echo(f"{issue.level.upper()} {issue.code}: {issue.message}" + (f" [{issue.path}]" if issue.path else ""))
    errors = [issue for issue in registry.issues if issue.level == "error"]
    if errors:
        raise click.ClickException(f"{len(errors)} correction pack error(s)")
    click.echo(f"OK: {len(registry.packs)} correction pack(s) are valid")


@ocr_correction.command("list-packs")
@click.option("--json-output", is_flag=True, help="Print machine-readable JSON")
def list_packs(json_output: bool) -> None:
    """List installed correction packs."""
    summaries = CorrectionPackRegistry.default().summaries()
    if json_output:
        click.echo(json.dumps(summaries, ensure_ascii=False, indent=2))
        return
    for item in summaries:
        scope = "/".join(str(item[key]) for key in ("locale", "language", "country") if item.get(key)) or "global"
        click.echo(f"{item['pack_id']}@{item['version']} priority={item['priority']} scope={scope}")


@ocr_correction.command("explain")
@click.argument("text")
@click.option("--role", default="unknown", show_default=True)
@click.option("--domain", default=None)
@click.option("--language", default=None)
@click.option("--country", default=None)
@click.option("--locale", default=None)
@click.option("--pack", "pack_ids", multiple=True)
@click.option("--mode", type=click.Choice(["safe", "suggest", "off"]), default="safe", show_default=True)
def explain(
    text: str,
    role: str,
    domain: str | None,
    language: str | None,
    country: str | None,
    locale: str | None,
    pack_ids: tuple[str, ...],
    mode: str,
) -> None:
    """Explain the deterministic decision for one OCR text fragment."""
    decision = SafeOCRCorrector().correct(
        text,
        CorrectionContext(
            role=role,
            domain=domain,
            language=language,
            country=country,
            locale=locale,
            pack_ids=pack_ids,
            mode=mode,  # type: ignore[arg-type]
        ),
    )
    click.echo(json.dumps(decision.to_dict(), ensure_ascii=False, indent=2))


@ocr_correction.command("evaluate")
@click.argument("samples", type=click.Path(path_type=Path, exists=True))
@click.option("--fail-on-regression", is_flag=True, help="Exit non-zero when any sample fails")
def evaluate(samples: Path, fail_on_regression: bool) -> None:
    """Evaluate JSON/JSONL/YAML golden samples."""
    loaded = load_evaluation_samples(samples)
    report = evaluate_samples(loaded)
    click.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    if fail_on_regression and report.passed != report.total:
        raise click.ClickException(f"{report.total - report.passed} sample(s) failed")


@ocr_correction.command("export-candidates")
@click.argument("mirror_json", type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.argument("output", type=click.Path(path_type=Path, dir_okay=False))
def export_candidates(mirror_json: Path, output: Path) -> None:
    """Export suggested/applied Mirror audit events as reviewable JSONL."""
    payload = json.loads(mirror_json.read_text(encoding="utf-8"))
    indexes = ((payload.get("evidence") or {}).get("indexes") or {}).get("ocr_corrections") or {}
    events = list(indexes.values()) if isinstance(indexes, dict) else list(indexes or [])
    count = write_feedback_jsonl(feedback_from_events(events), output)
    click.echo(f"Wrote {count} candidate(s) to {output.resolve()}")


__all__ = ["ocr_correction"]
