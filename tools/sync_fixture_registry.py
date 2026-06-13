#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generate tests/fixtures/registry.yaml from on-disk fixture tree."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
REGISTRY_PATH = FIXTURES_DIR / "registry.yaml"
TEXT_SAMPLES = FIXTURES_DIR / "text_samples"

# Git LFS policy threshold (see docs/design/10_test_architecture_first_principles_redesign.md §9)
LFS_THRESHOLD_BYTES = 10_000_000

_TRANSPORT = {
    ".pdf": "pdf",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".txt": "text",
}

# Parent dir → default tracks (P0 scenes with community plugins or TQG coverage)
_TRACKS_BY_TYPE: dict[str, list[str]] = {
    "wechat_payment": ["extract", "classify", "edition"],
    "alipay_payment": ["extract", "classify"],
    "bank_statement": ["extract", "classify", "mirror"],
    "id_card": ["classify", "mirror", "extract"],
    "business_license": ["classify", "mirror", "extract"],
    "vat_invoice": ["classify"],
}


def _size_label(num_bytes: int) -> str:
    if num_bytes >= LFS_THRESHOLD_BYTES:
        return "lfs_candidate"
    if num_bytes > 5_000_000:
        return "large"
    if num_bytes > 500_000:
        return "medium"
    return "small"


def _asset_meta(size: int) -> dict:
    meta: dict = {"size_bytes": size}
    if size >= LFS_THRESHOLD_BYTES:
        meta["lfs"] = True
    return meta


def _collect_assets() -> list[dict]:
    assets: list[dict] = []
    if TEXT_SAMPLES.is_dir():
        for path in sorted(TEXT_SAMPLES.glob("*.txt")):
            scene = path.stem
            size = path.stat().st_size
            assets.append(
                {
                    "path": f"text_samples/{path.name}",
                    "document_type": scene,
                    "transport": "text",
                    "tiers": ["regression"],
                    "tracks": ["classify"],
                    "bytes": _size_label(size),
                    "pii": "scrubbed",
                    "source": "text_sample",
                    **(_asset_meta(size)),
                }
            )

    for path in sorted(FIXTURES_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "registry.yaml":
            continue
        if "text_samples" in path.parts:
            continue
        rel = path.relative_to(FIXTURES_DIR).as_posix()
        doc_type = path.parent.name
        if doc_type == "fixtures" or doc_type == "tests":
            continue
        ext = path.suffix.lower()
        transport = _TRANSPORT.get(ext, "unknown")
        size = path.stat().st_size
        tracks = list(_TRACKS_BY_TYPE.get(doc_type, ["classify"]))
        tiers = ["regression"]
        if doc_type in ("wechat_payment",) and size > 1_000_000:
            tiers.append("slow")
        assets.append(
            {
                "path": rel,
                "document_type": doc_type,
                "transport": transport,
                "tiers": tiers,
                "tracks": tracks,
                "bytes": _size_label(size),
                "pii": "scrubbed",
                **(_asset_meta(size)),
            }
        )
    return assets


def main() -> int:
    assets = _collect_assets()
    payload = {
        "version": 1,
        "description": "Auto-generated fixture registry — run tools/sync_fixture_registry.py to refresh",
        "asset_count": len(assets),
        "assets": assets,
    }
    REGISTRY_PATH.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(assets)} assets to {REGISTRY_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
