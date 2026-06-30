# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TQG regression tier — manifest parametrization hooks."""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

from docmirror.eval.tqg.manifest import TQG_GATES_DIR, TQGCase, load_track_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
TQG_REPORT_DIR = REPO_ROOT / "artifacts" / "tqg"
RUN_PRIVATE_FIXTURES = os.environ.get("DOCMIRROR_RUN_PRIVATE_FIXTURES") == "1"


def _cases_for_track(track_file: str) -> list[TQGCase]:
    path = TQG_GATES_DIR / track_file
    return load_track_manifest(path, repo_root=REPO_ROOT)


def _edition_package_available(edition: str) -> bool:
    modules = {"enterprise": "docmirror_enterprise", "finance": "docmirror_finance"}
    module_path = modules.get(edition)
    if not module_path:
        return True
    try:
        importlib.import_module(module_path)
        return True
    except ImportError:
        return False


def _is_private_fixture(path: Path) -> bool:
    try:
        rel = path.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return False
    return len(rel.parts) >= 2 and rel.parts[:2] == ("tests", "fixtures")


@pytest.fixture(scope="session")
def tqg_report_dir() -> Path:
    path = Path(os.environ.get("TQG_REPORT_DIR", TQG_REPORT_DIR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run_and_assert(case: TQGCase, tqg_report_dir: Path | None = None) -> None:
    from docmirror.eval.tqg.runner import run_tqg_case

    if case.optional_edition and case.editions:
        for edition in case.editions:
            if edition in ("enterprise", "finance") and not _edition_package_available(edition):
                pytest.skip(f"optional edition package missing: {edition}")

    if case.fixture and _is_private_fixture(case.fixture) and not RUN_PRIVATE_FIXTURES:
        pytest.skip("private fixture gated; set DOCMIRROR_RUN_PRIVATE_FIXTURES=1 to run")
    if case.fixture and not case.fixture.is_file():
        pytest.skip(f"fixture missing: {case.fixture}")
    report = run_tqg_case(case)
    if tqg_report_dir is not None:
        out = tqg_report_dir / f"{case.track}_{case.id}.json"
        out.write_text(report.to_json(), encoding="utf-8")
    if case.optional_edition and report.metrics.get("edition_skipped"):
        pytest.skip(f"optional edition skipped: {report.metrics['edition_skipped']}")
    assert report.passed, (
        f"case_id={report.case_id} track={report.track} failure_class={report.failure_class} "
        f"failures={report.failures}"
    )


_EXTRACT_CASES = _cases_for_track("extract.yaml")
_CLASSIFY_CASES = _cases_for_track("classify.yaml")
_MIRROR_CASES = _cases_for_track("mirror.yaml")
_EDITION_CASES = _cases_for_track("edition.yaml")
_TRANSPORT_CASES = _cases_for_track("transport.yaml")
_E2E_CASES = _cases_for_track("e2e.yaml")
_LICENSING_CASES = _cases_for_track("licensing.yaml")
