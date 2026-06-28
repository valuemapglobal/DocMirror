from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_public_trust_quickstart_runs() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "trust_quickstart.py")],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )

    output = result.stdout
    assert "DocMirror trust quickstart" in output
    assert "field=invoice_number" in output
    assert "source_ref=synthetic_invoice_001#page=1" in output
    assert "review_required:true" in output
