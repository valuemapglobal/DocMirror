# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.ocr import pipeline as uop


def test_uop_exports_run_scanned_page():
    assert callable(uop.run_scanned_page)
    assert uop.analyze_scanned_page is uop.run_scanned_page
