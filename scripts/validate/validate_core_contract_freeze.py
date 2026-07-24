#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate the semantic P1 core-contract snapshot."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docmirror/configs/stability/core_contract_manifest.json"
PYPROJECT = ROOT / "pyproject.toml"

FUNCTIONS = {
    "dispatcher.process": ("docmirror/framework/dispatcher.py", "ParserDispatcher", "process"),
    "canonical.assemble": ("docmirror/input/canonical/assembler.py", None, "assemble_parse_result"),
    "canonical.seal": ("docmirror/input/canonical/seal.py", None, "seal_canonical_result"),
    "output.build_community": ("docmirror/server/output_builder.py", None, "build_community_projection"),
    "output.build_all": ("docmirror/server/output_builder.py", None, "build_all_projections"),
    "projector.mirror": ("docmirror/output/mirror_projector.py", None, "project_mirror"),
    "projector.community": ("docmirror/output/community_bundle.py", None, "project_community_bundle"),
}


def _annotation(value: ast.expr | None) -> str:
    return ast.unparse(value) if value is not None else ""


def _function_contract(relative: str, class_name: str | None, function_name: str) -> dict[str, Any]:
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"), filename=relative)
    candidates: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in tree.body:
        if (
            class_name is None
            and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ):
            candidates.append(node)
        elif isinstance(node, ast.ClassDef) and node.name == class_name:
            candidates.extend(
                child
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == function_name
            )
    if len(candidates) != 1:
        raise ValueError(f"expected one {relative}:{class_name or ''}.{function_name}; got {len(candidates)}")
    node = candidates[0]
    positional = [*node.args.posonlyargs, *node.args.args]
    defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
    args = [
        {
            "name": arg.arg,
            "kind": "positional",
            "annotation": _annotation(arg.annotation),
            "default": ast.unparse(default) if default is not None else None,
        }
        for arg, default in zip(positional, defaults)
        if arg.arg not in {"self", "cls"}
    ]
    args.extend(
        {
            "name": arg.arg,
            "kind": "keyword_only",
            "annotation": _annotation(arg.annotation),
            "default": ast.unparse(default) if default is not None else None,
        }
        for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults)
    )
    return {
        "async": isinstance(node, ast.AsyncFunctionDef),
        "arguments": args,
        "return": _annotation(node.returns),
    }


def build_snapshot() -> dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    from docmirror.models.entities.parse_result import ParseResult
    from docmirror.plugin_api import PluginProvider
    from docmirror.plugins._base.projector import ProjectionData

    return {
        "schema_version": "docmirror.contract_core.v1",
        "models": {
            "ParseResult": ParseResult.model_json_schema(),
            "ProjectionData": ProjectionData.model_json_schema(),
            "PluginProvider": {
                name: {
                    "annotation": str(field.annotation),
                    "required": field.is_required(),
                    "default": repr(field.default) if not field.is_required() else None,
                }
                for name, field in PluginProvider.model_fields.items()
            },
        },
        "functions": {name: _function_contract(*definition) for name, definition in sorted(FUNCTIONS.items())},
    }


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    raw = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def candidate_identity_errors(manifest: dict[str, Any], project_version: str) -> list[str]:
    candidate = str(manifest.get("candidate") or "")
    if candidate != project_version:
        return [f"core contract candidate {candidate or '<missing>'} != package version {project_version}"]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-hash", action="store_true")
    parser.add_argument("--require-qualified", action="store_true")
    args = parser.parse_args(argv)
    actual = snapshot_hash(build_snapshot())
    if args.print_hash:
        print(actual)
        return 0
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    project_version = str(tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"])
    identity_errors = candidate_identity_errors(manifest, project_version)
    if identity_errors:
        print("Core contract release identity FAILED:", file=sys.stderr)
        for error in identity_errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    expected = str(manifest.get("contract_sha256") or "")
    if actual != expected:
        print("Core contract freeze FAILED:", file=sys.stderr)
        print(f"  expected: {expected}", file=sys.stderr)
        print(f"  actual:   {actual}", file=sys.stderr)
        return 1
    if args.require_qualified:
        errors: list[str] = []
        qualification = manifest.get("qualification") or {}
        if qualification.get("status") != "qualified":
            errors.append("current contract snapshot is not technically qualified")
        if qualification.get("contract_sha256") != expected:
            errors.append("qualified contract fingerprint differs from the frozen snapshot")
        if errors:
            print("Core stability qualification FAILED:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            return 1
    print(f"Core contract freeze OK ({actual[:16]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
