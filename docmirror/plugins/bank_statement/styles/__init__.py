# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Bank statement style parser modules package.

Each submodule implements one ledger layout family (grid, compact merged, signed
amount, borderless OCR, KV identity, row pair merge). Imported by
``style_registry`` via parser ID map — not used directly by ``runner``.

Pipeline role: style-specific extract invoked after ``BankStyleDetector`` classification.
"""
