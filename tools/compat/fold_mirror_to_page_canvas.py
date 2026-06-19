#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fold legacy mirror JSON into page-centric PageCanvas regions (offline compat)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mirror_json", type=Path, help="Path to *_mirror.json")
    parser.add_argument("--page", type=int, default=0, help="Validate single page (0 = all)")
    parser.add_argument("--validate", action="store_true", help="Compare legacy vs folded region counts")
    parser.add_argument("--output", type=Path, default=None, help="Write folded document JSON")
    args = parser.parse_args()

    from docmirror.models.mirror.legacy_project import fold_legacy_mirror_document

    payload = json.loads(args.mirror_json.read_text(encoding="utf-8"))
    document = ((payload.get("data") or {}).get("document") or {})
    folded_doc = fold_legacy_mirror_document(document)

    if args.validate:
        legacy_grids = list(document.get("micro_grids") or [])
        legacy_structures = [
            s
            for ev in (document.get("scanned_local_structure_evidence") or [])
            if isinstance(ev, dict)
            for s in (ev.get("structures") or [])
        ]
        if args.page:
            legacy_grids = [
                g for g in legacy_grids
                if isinstance(g, dict) and int(g.get("page") or 0) == args.page
            ]
            legacy_structures = [
                s
                for ev in (document.get("scanned_local_structure_evidence") or [])
                if isinstance(ev, dict) and int(ev.get("page") or 0) == args.page
                for s in (ev.get("structures") or [])
                if isinstance(s, dict)
            ]
        folded_regions = []
        for page in folded_doc.get("pages") or []:
            if args.page and int(page.get("page_number") or 0) != args.page:
                continue
            folded_regions.extend(page.get("regions") or [])
        grid_regions = [r for r in folded_regions if r.get("kind") == "micro_grid"]
        field_regions = [r for r in folded_regions if r.get("kind") in {"field_grid", "label_value_graph"}]
        print(f"legacy micro_grids: {len(legacy_grids)}")
        print(f"legacy local structures: {len(legacy_structures)}")
        print(f"folded micro_grid regions: {len(grid_regions)}")
        print(f"folded field_grid regions: {len(field_regions)}")
        if len(legacy_grids) != len(grid_regions):
            print("WARN: micro_grid count mismatch", file=sys.stderr)
            return 1
        if legacy_structures and len(field_regions) < len(legacy_structures):
            print("WARN: field_grid region count lower than legacy structures", file=sys.stderr)
            return 1

    if args.output:
        out_payload = dict(payload)
        out_payload.setdefault("data", {})["document"] = folded_doc
        args.output.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
