# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
P0 Input Coverage Matrix Validator
===================================

Verifies that every P0 input category in the GA 1.0 input coverage plan has
a corresponding FCR entry, support matrix entry, and (where applicable) an
adapter binding.

Run::

    python3 scripts/validate_input_p0_matrix.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path
_PROJ = Path(__file__).resolve().parent.parent
if str(_PROJ) not in sys.path:
    sys.path.insert(0, str(_PROJ))

from docmirror.configs.format.loader import load_format_registry
from docmirror.configs.format.resolver import resolve_capability
from docmirror.configs.support_matrix import load_support_matrix

# ── P0 input categories ─────────────────────────────────────────────────────
P0_CATEGORIES = {
    # (test_name, file_suffix, capability_id, mime_type)
    "pdf_native": (".pdf", "pdf_native", "application/pdf"),
    "image_png": (".png", "image_raster", "image/png"),
    "image_jpg": (".jpg", "image_raster", "image/jpeg"),
    "image_tiff": (".tiff", "image_raster", "image/tiff"),
    "image_webp": (".webp", "image_raster", "image/webp"),
    "image_bmp": (".bmp", "image_raster", "image/bmp"),
    "word_docx": (".docx", "word_docx", ""),
    "excel_xlsx": (".xlsx", "excel_xlsx", ""),
    "ppt_pptx": (".pptx", "ppt_pptx", ""),
    "html": (".html", "web_html", ""),
    "email_eml": (".eml", "email_eml", ""),
    "archive_zip": (".zip", "archive_zip", "application/zip"),
}

REQUIRED_EXTS = {
    "pdf_native": ".pdf",
    "image_png": ".png",
    "image_webp": ".webp",
    "word_docx": ".docx",
}


def check_fcr() -> list[str]:
    errors = []
    caps, _ext_map, mime_map = load_format_registry()
    cap_ids = set(caps.keys())

    for name, (ext, cap_id, mime) in P0_CATEGORIES.items():
        if cap_id not in cap_ids:
            errors.append(f"FCR MISSING capability {cap_id} ({name})")

    if errors:
        print("\n  FCR Errors:")
        for e in errors:
            print(f"    FAIL: {e}")
    else:
        print("  FCR: ALL PASS")
    return errors


def check_support_matrix() -> list[str]:
    errors = []
    matrix = load_support_matrix()
    formats = matrix.get("formats", {})

    for name, (ext, cap_id, mime) in P0_CATEGORIES.items():
        if cap_id not in formats:
            errors.append(f"SUPPORT MATRIX MISSING capability {cap_id} ({name})")
        else:
            info = formats[cap_id]
            if ext not in info.get("inputs", []):
                errors.append(f"SUPPORT MATRIX MISSING extension {ext} in {cap_id} ({name})")

    if errors:
        print("\n  Support Matrix Errors:")
        for e in errors:
            print(f"    FAIL: {e}")
    else:
        print("  Support Matrix: ALL PASS")
    return errors


def check_resolver() -> list[str]:
    errors = []
    for name, (ext, expected_cap_id, mime) in P0_CATEGORIES.items():
        # Create a mock path
        p = Path(f"/tmp/test{ext}")
        try:
            cap = resolve_capability(p, mime)
            if cap.id != expected_cap_id:
                errors.append(f"RESOLVER: {name} → got capability {cap.id}, expected {expected_cap_id}")
        except Exception as e:
            errors.append(f"RESOLVER EXCEPTION for {name}: {e}")

    if errors:
        print("\n  Resolver Errors:")
        for e in errors:
            print(f"    FAIL: {e}")
    else:
        print("  Resolver: ALL PASS")
    return errors


def check_human_todo() -> list[str]:
    """Items that require manual verification or cannot be automated."""
    print("\n  Manual verification required:")
    print("    - Validate docmirror parse scan.webp returns success or INVALID_IMAGE")
    print("    - Validate encrypted.pdf returns ENCRYPTED_PDF with suggestion")
    print("    - Validate damaged.pdf returns DAMAGED_PDF with suggestion")
    print("    - Validate tiny.bin returns FILE_TOO_SMALL")
    print("    - Validate large.pdf over limit returns FILE_TOO_LARGE")
    print("    - Validate invalid.png returns INVALID_IMAGE")
    print("    - Validate low-quality image returns LOW_QUALITY_IMAGE with needs_review")
    print("    - Validate zip bomb returns ARCHIVE_RESOURCE_LIMIT")
    print("    - Validate zip path traversal returns ARCHIVE_UNSAFE_PATH")
    print("    - Validate password zip returns ARCHIVE_PASSWORD_PROTECTED")
    print("    - Validate unsupported.xyz returns UNSUPPORTED_FORMAT with suggestion")
    print("    - Validate archiver DOC/XLS/PPT missing converter returns FORMAT_REQUIRES_CONVERTER")
    return []


def main() -> int:
    print("=" * 60)
    print("  P0 Input Coverage Matrix Validator")
    print("=" * 60)

    all_errors = []
    all_errors += check_fcr()
    all_errors += check_support_matrix()
    all_errors += check_resolver()
    check_human_todo()

    if all_errors:
        print(f"\n{'=' * 60}")
        print(f"  FAILED: {len(all_errors)} validation error(s)")
        print(f"{'=' * 60}")
        return 1
    else:
        print(f"\n{'=' * 60}")
        print("  ALL P0 VALIDATIONS PASSED")
        print(f"{'=' * 60}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
