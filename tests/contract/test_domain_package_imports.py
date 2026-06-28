from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_new_domain_packages_import_without_optional_dependencies() -> None:
    script = """
import importlib
import sys
for name in (
    'docmirror.layout',
    'docmirror.ocr',
    'docmirror.tables',
    'docmirror.topology',
    'docmirror.geometry',
):
    importlib.import_module(name)
for forbidden in ('numpy', 'cv2', 'fitz', 'rapidocr_onnxruntime', 'onnxruntime'):
    assert forbidden not in sys.modules, forbidden
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
