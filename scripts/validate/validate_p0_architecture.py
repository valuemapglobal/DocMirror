#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Enforce ADR 0002 P0 fact-pipeline and projection boundaries."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCMIRROR = ROOT / "docmirror"

REQUIRED_FILES = (
    ROOT / "docs/adr/0002-p0-canonical-fact-pipeline.md",
    DOCMIRROR / "plugin_api.py",
    DOCMIRROR / "input/canonical/fact_patch.py",
    DOCMIRROR / "input/canonical/seal.py",
    DOCMIRROR / "models/sealed.py",
    DOCMIRROR / "output/mirror_projector.py",
)

CANONICAL_FILES = (
    *tuple((DOCMIRROR / "input/canonical").rglob("*.py")),
    DOCMIRROR / "framework/middlewares/extraction/community_fact_recognizer.py",
)

CANONICAL_FORBIDDEN_IMPORTS = (
    "docmirror.models.edition_serializer",
    "docmirror.output",
    "docmirror.plugins._runtime.licensing",
    "docmirror.server",
)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.append(node.module)
    return result


def main() -> int:
    errors: list[str] = []
    for path in REQUIRED_FILES:
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            errors.append(f"required P0 architecture file missing or empty: {path.relative_to(ROOT)}")
    if not CANONICAL_FILES:
        errors.append("canonical source scan is empty")

    for path in CANONICAL_FILES:
        for imported in _imports(path):
            if any(imported == prefix or imported.startswith(prefix + ".") for prefix in CANONICAL_FORBIDDEN_IMPORTS):
                errors.append(f"canonical delivery dependency: {path.relative_to(ROOT)} -> {imported}")

    recognizer_source = (DOCMIRROR / "framework/middlewares/extraction/community_fact_recognizer.py").read_text(
        encoding="utf-8"
    )
    for required in ("run_fact_recognition_sync", "apply_fact_patch"):
        if required not in recognizer_source:
            errors.append(f"CommunityFactRecognizer missing canonical boundary call: {required}")
    for forbidden in ("run_plugin_extract", "edition_serializer", "merge_plugin_projection"):
        if forbidden in recognizer_source:
            errors.append(f"CommunityFactRecognizer contains delivery/write-back path: {forbidden}")

    if (DOCMIRROR / "plugins/_runtime/parse_result_enrichment.py").exists():
        errors.append("legacy edition-payload-to-ParseResult write-back module still exists")
    if (DOCMIRROR / "plugins/_runtime/legacy_fact_patch.py").exists():
        errors.append("legacy edition-envelope-to-FactPatch adapter still exists")

    runner_source = (DOCMIRROR / "plugins/_runtime/runner.py").read_text(encoding="utf-8")
    if "merge_plugin_projection_into_parse_result" in runner_source:
        errors.append("plugin runner still writes an edition projection into ParseResult")
    if "legacy_payload_to_fact_patch" in runner_source:
        errors.append("canonical recognition still adapts an edition envelope")

    parse_result_source = (DOCMIRROR / "models/entities/parse_result.py").read_text(encoding="utf-8")
    for forbidden in ("to_mirror_json_vnext", "MirrorCoreVNext", "project_mirror"):
        if forbidden in parse_result_source:
            errors.append(f"ParseResult still owns output projection behavior: {forbidden}")

    dispatcher_source = (DOCMIRROR / "framework/dispatcher.py").read_text(encoding="utf-8")
    if "seal_canonical_result(result)" not in dispatcher_source:
        errors.append("Dispatcher does not cross the final canonical seal gate")

    middleware_source = (DOCMIRROR / "framework/middlewares/base.py").read_text(encoding="utf-8")
    for required in ("canonical_fact_diff", "canonical mutation audit gap", "failed after changing canonical facts"):
        if required not in middleware_source:
            errors.append(f"middleware fact-mutation audit missing: {required}")

    fact_patch_source = (DOCMIRROR / "input/canonical/fact_patch.py").read_text(encoding="utf-8")
    for required in ("replacement requires evidence_ids", "cites unknown evidence_ids", "replace_paths"):
        if required not in fact_patch_source:
            errors.append(f"FactPatch replacement evidence gate missing: {required}")

    output_source = (DOCMIRROR / "server/output_builder.py").read_text(encoding="utf-8")
    for required in ("seal_parse_result", "project_mirror", "sealed.to_read_view()"):
        if required not in output_source:
            errors.append(f"projection builder missing sealed boundary: {required}")

    for path in DOCMIRROR.rglob("*.py"):
        if path == DOCMIRROR / "server/output_builder.py":
            continue
        if "build_community_output" in path.read_text(encoding="utf-8"):
            errors.append(f"production dependency on compatibility Community output: {path.relative_to(ROOT)}")

    input_source = (DOCMIRROR / "input/acceptance.py").read_text(encoding="utf-8")
    model_source = (DOCMIRROR / "input/models.py").read_text(encoding="utf-8")
    for required, source in (
        ("_materialize_content_snapshot", input_source),
        ("verify_content_identity", model_source),
        ("owns_snapshot", model_source),
    ):
        if required not in source:
            errors.append(f"AcceptedSource content binding missing: {required}")

    writer_imports = _imports(DOCMIRROR / "server/artifact_writer.py")
    for imported in writer_imports:
        if imported.startswith("docmirror.models.entities.parse_result") or imported.startswith("docmirror.plugins"):
            errors.append(f"ArtifactWriter crosses fact/plugin boundary: {imported}")

    if errors:
        print("P0 architecture validation FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"P0 architecture validation OK ({len(CANONICAL_FILES)} canonical files checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
