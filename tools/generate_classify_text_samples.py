#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generate keyword-rich text_samples/*.txt from scene_keywords.yaml for classify TQG."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENE_KEYWORDS = REPO_ROOT / "docmirror" / "configs" / "yaml" / "scene_keywords.yaml"
TEXT_SAMPLES = REPO_ROOT / "tests" / "fixtures" / "text_samples"
CLASSIFY_MANIFEST = REPO_ROOT / "docmirror" / "configs" / "yaml" / "test" / "gates" / "classify.yaml"


def _load_scenes() -> dict[str, dict]:
    data = yaml.safe_load(SCENE_KEYWORDS.read_text(encoding="utf-8")) or {}
    return data.get("scene_keywords") or data


def _covered_scenes() -> set[str]:
    covered: set[str] = set()
    if CLASSIFY_MANIFEST.is_file():
        manifest = yaml.safe_load(CLASSIFY_MANIFEST.read_text(encoding="utf-8")) or {}
        for case in manifest.get("cases") or []:
            gates = case.get("gates") or {}
            dt = gates.get("document_type") or {}
            if "equals" in dt:
                covered.add(str(dt["equals"]))
    for path in TEXT_SAMPLES.glob("*.txt"):
        covered.add(path.stem)
    return covered


def _sample_text(scene: str, keywords: list[str]) -> str:
    title = keywords[0] if keywords else scene.replace("_", " ").title()
    lines = [title, f"文档类型：{scene}", ""]
    for kw in keywords[:8]:
        if kw not in lines[0]:
            lines.append(kw)
    lines.append("")
    lines.append("（自动化 classify_text 回归样例 — 关键词来自 scene_keywords.yaml）")
    return "\n".join(lines) + "\n"


def generate(scenes: list[str], *, dry_run: bool = False) -> list[str]:
    corpus = _load_scenes()
    TEXT_SAMPLES.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for scene in scenes:
        entry = corpus.get(scene)
        if not entry:
            print(f"skip unknown scene: {scene}", file=sys.stderr)
            continue
        kws = list(entry.get("include") or [])[:8]
        text = _sample_text(scene, kws)
        path = TEXT_SAMPLES / f"{scene}.txt"
        if dry_run:
            print(f"would write {path}")
        else:
            path.write_text(text, encoding="utf-8")
            written.append(scene)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate classify text_samples from scene_keywords")
    parser.add_argument(
        "--scenes",
        nargs="*",
        help="Explicit scene ids (default: next uncovered P1 batch up to --limit)",
    )
    parser.add_argument("--limit", type=int, default=20, help="Max new scenes when auto-selecting")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.scenes:
        targets = args.scenes
    else:
        covered = _covered_scenes()
        all_scenes = sorted(_load_scenes().keys())
        targets = [s for s in all_scenes if s not in covered][: args.limit]

    written = generate(targets, dry_run=args.dry_run)
    if not args.dry_run and written:
        _sync_classify_manifest(written)
    if not args.dry_run:
        print(f"Generated {len(written)} text samples: {', '.join(written)}")
    return 0


def _sync_classify_manifest(scenes: list[str]) -> None:
    """Append classify_text cases for new text_samples."""
    if not CLASSIFY_MANIFEST.is_file():
        return
    data = yaml.safe_load(CLASSIFY_MANIFEST.read_text(encoding="utf-8")) or {}
    cases = list(data.get("cases") or [])
    existing_ids = {c.get("id") for c in cases}
    for scene in scenes:
        cid = f"{scene}_text"
        if cid in existing_ids:
            continue
        cases.append(
            {
                "id": cid,
                "tier": "regression",
                "fixture": f"fixtures/text_samples/{scene}.txt",
                "pipeline": "classify_text",
                "gates": {"document_type": {"equals": scene}},
                "tags": ["text_sample", "auto_batch"],
            }
        )
    data["cases"] = cases
    CLASSIFY_MANIFEST.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Synced {len(scenes)} cases into classify.yaml")


if __name__ == "__main__":
    sys.exit(main())
