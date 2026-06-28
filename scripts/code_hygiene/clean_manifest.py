# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Clean architecture manifest loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from scripts.code_hygiene.config import ROOT

CLEAN_MANIFEST_PATH = ROOT / "docmirror" / "configs" / "architecture" / "clean_manifest.yaml"


@dataclass(frozen=True)
class CleanManifest:
    path: Path
    data: dict[str, Any]

    def modules_for(self, section: str) -> set[str]:
        values = self.data.get(section) or []
        out: set[str] = set()
        for item in values:
            if isinstance(item, str):
                out.add(item)
            elif isinstance(item, dict) and item.get("module"):
                out.add(str(item["module"]))
            elif isinstance(item, dict) and item.get("old"):
                out.add(str(item["old"]))
        return out

    @property
    def public_modules(self) -> set[str]:
        return self.modules_for("public_modules")

    @property
    def dynamic_modules(self) -> set[str]:
        return self.modules_for("dynamic_modules")

    @property
    def compatibility_modules(self) -> set[str]:
        return self.modules_for("compatibility_modules")

    @property
    def removed_modules(self) -> set[str]:
        return self.modules_for("removed_modules")

    @property
    def quarantine_modules(self) -> set[str]:
        return self.modules_for("quarantine_modules")

    @property
    def live_modules(self) -> set[str]:
        return self.public_modules | self.dynamic_modules | self.compatibility_modules | self.quarantine_modules


def load_clean_manifest(path: Path = CLEAN_MANIFEST_PATH) -> CleanManifest:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Clean manifest must contain a mapping: {path}")
    return CleanManifest(path=path, data=data)


def is_manifest_live_module(module: str, manifest: CleanManifest | None = None) -> bool:
    manifest = manifest or load_clean_manifest()
    live = manifest.live_modules
    return module in live or any(module.startswith(prefix + ".") for prefix in live)

