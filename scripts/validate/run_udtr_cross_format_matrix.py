#!/usr/bin/env python3
"""Run UDTR cross-format source fixtures and validate their Mirror outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate.validate_udtr_golden import summarize_manifest_file, validate_manifest_file


def run_cross_format_matrix(
    manifest_path: Path,
    *,
    allow_missing_private: bool = True,
) -> dict[str, Any]:
    base_dir = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = manifest.get("cases") if isinstance(manifest.get("cases"), list) else []
    processed: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    core: Any | None = None

    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"case:{index}: case must be an object")
            continue
        case_id = str(case.get("case_id") or f"case:{index}")
        source_path = case.get("source_path")
        if not source_path:
            skipped.append(case_id)
            continue
        source = _resolve_case_path(source_path, base_dir=base_dir)
        if not source.exists():
            if allow_missing_private and (case.get("private_source") is True or case.get("skip_if_missing") is True):
                skipped.append(case_id)
                continue
            errors.append(f"{case_id}: source_path not found: {source}")
            continue
        output_path_value = case.get("mirror_output")
        if not output_path_value:
            errors.append(f"{case_id}: mirror_output is required when source_path is provided")
            continue
        output_path = _resolve_case_path(output_path_value, base_dir=base_dir)
        try:
            from docmirror.models.mirror.core import MirrorCoreVNext, MirrorOptions

            if core is None:
                core = MirrorCoreVNext()
            payload = core.process(source, MirrorOptions(source_filename=str(source))).to_dict()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            processed.append(case_id)
        except Exception as exc:
            errors.append(f"{case_id}: UDTR processing failed: {exc}")

    validation_errors = validate_manifest_file(manifest_path, allow_missing_private=allow_missing_private)
    summary = summarize_manifest_file(manifest_path, allow_missing_private=allow_missing_private)
    return {
        "manifest": str(manifest_path),
        "processed_case_ids": processed,
        "skipped_case_ids": skipped,
        "processing_errors": errors,
        "validation_errors": validation_errors,
        "summary": summary,
        "status": "ok" if not errors and not validation_errors else "failed",
    }


def _resolve_case_path(value: Any, *, base_dir: Path) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else base_dir / path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run UDTR cross-format matrix manifest")
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--strict-private",
        action="store_true",
        help="Fail when a private/skip-if-missing source or output is absent.",
    )
    parser.add_argument("--summary-json", type=Path, help="Write the run report JSON.")
    args = parser.parse_args()
    report = run_cross_format_matrix(args.manifest, allow_missing_private=not args.strict_private)
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if report["status"] != "ok":
        print("UDTR cross-format matrix FAILED")
        for error in report["processing_errors"]:
            print(f"- {error}")
        for error in report["validation_errors"]:
            print(f"- {error}")
        return 1
    print("UDTR cross-format matrix OK")
    print(f"processed={len(report['processed_case_ids'])} skipped={len(report['skipped_case_ids'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
