#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Generate import-linter config from the clean architecture manifest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.code_hygiene.clean_manifest import load_clean_manifest  # noqa: E402

OUTPUT_PATH = REPO_ROOT / ".importlinter"


def _layer_module_from_glob(glob: str) -> str | None:
    prefix = glob.split("/**", 1)[0].strip("/")
    if not prefix.startswith("docmirror/"):
        return None
    return prefix.replace("/", ".")


def render_import_linter(data: dict[str, Any]) -> str:
    lines: list[str] = [
        "# DocMirror Import Dependency Contract",
        "#",
        "# Generated from docmirror/configs/architecture/clean_manifest.yaml.",
        "# Run: python3 scripts/validate/generate_import_linter.py --check",
        "",
        "[importlinter]",
        "root_package = docmirror",
        "",
        "include_external_packages = True",
    ]

    contract_index = 1
    for layer_name, layer in (data.get("layers") or {}).items():
        forbidden = layer.get("forbidden_imports") or []
        if not forbidden:
            continue
        paths = layer.get("paths") or []
        modules = [_layer_module_from_glob(path) for path in paths]
        modules = [module for module in modules if module]
        if not modules:
            continue
        lines.extend(
            [
                "",
                f"[importlinter:manifest_forbidden_{contract_index}_{layer_name}]",
                f"name = Clean manifest forbidden imports for {layer_name}",
                "type = forbidden",
                "source_modules =",
            ]
        )
        for module in modules:
            lines.append(f"    {module}")
        lines.append("forbidden_modules =")
        for forbidden_module in forbidden:
            lines.append(f"    {forbidden_module}")
        if layer.get("import_linter_allow_indirect", False):
            lines.append("allow_indirect_imports = True")
        ignore_imports = layer.get("import_linter_ignore_imports") or []
        if ignore_imports:
            lines.append("ignore_imports =")
            for item in ignore_imports:
                lines.append(f"    {item['importer']} -> {item['imported']}")
        contract_index += 1

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if .importlinter is out of date")
    args = parser.parse_args()

    manifest = load_clean_manifest()
    rendered = render_import_linter(manifest.data)

    if args.check:
        current = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if current != rendered:
            print(".importlinter is out of date; run scripts/validate/generate_import_linter.py", file=sys.stderr)
            return 1
        print(".importlinter is up to date")
        return 0

    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
