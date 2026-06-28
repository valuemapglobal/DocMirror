#!/usr/bin/env python3
"""Public trust-layer quickstart using a synthetic artifact.

This example is intentionally dependency-light. It demonstrates the public
Parse + Prove + Trust contract without requiring private fixtures or OCR models.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARTIFACT = ROOT / "fixtures" / "trust_quickstart_artifact.json"


def main() -> None:
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    document = artifact["document"]
    trust = artifact["trust"]

    print("DocMirror trust quickstart")
    print(f"document={document['id']} type={document['type']}")
    print(
        "trust="
        f"confidence:{trust['document_confidence']:.2f} "
        f"evidence_coverage:{trust['evidence_coverage']:.2f} "
        f"review_required:{str(trust['review_required']).lower()}"
    )

    for field in artifact["fields"]:
        evidence = field["evidence"]
        review = "review" if field["needs_review"] else "ok"
        print(
            f"field={field['name']} value={field['value']} "
            f"confidence={field['confidence']:.2f} "
            f"page={evidence['page']} bbox={evidence['bbox']} "
            f"source_ref={evidence['source_ref']} status={review}"
        )


if __name__ == "__main__":
    main()
