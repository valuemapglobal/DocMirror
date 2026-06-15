# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Style detector pipe-ledger veto and forced split_debit_credit tests."""

from __future__ import annotations

from docmirror.plugins.bank_statement.context import StyleContext
from docmirror.plugins.bank_statement.ltro import ReconstructionMeta
from docmirror.plugins.bank_statement.style_detector import BankStyleDetector
from tests.unit.test_bank_styles_signed_amount import SIGNED_TABLE
from tests.unit.test_pipe_text_table_builder import BOC_HEADER, BOC_ROW1, _synthetic_boc_text


def test_force_split_on_pipe_reconstruction():
    from docmirror.plugins.bank_statement.pipe_text_table_builder import build_tables_from_pipe_text

    text = _synthetic_boc_text()
    tables = build_tables_from_pipe_text(text)
    ctx = StyleContext(
        tables=tables,
        full_text=text,
        institution="中国银行",
        page_count=1,
        reconstruction=ReconstructionMeta(
            source="pipe_text",
            expected_primary_rows=1,
            pipe_header_detected=True,
        ),
    )
    detection = BankStyleDetector().detect(ctx)
    assert detection.primary_style == "split_debit_credit"


def test_signed_amount_veto_on_pipe_text():
    text = _synthetic_boc_text()
    ctx = StyleContext(
        tables=SIGNED_TABLE,
        full_text=text,
        institution=None,
        page_count=1,
        reconstruction=ReconstructionMeta(
            source="pipe_text",
            expected_primary_rows=1,
            pipe_header_detected=True,
        ),
    )
    detection = BankStyleDetector().detect(ctx)
    assert detection.primary_style != "signed_amount"


def test_signed_amount_still_works_for_spaced_ocr():
    ctx = StyleContext(
        tables=SIGNED_TABLE,
        full_text="符号金额银行流水",
        institution=None,
        page_count=1,
        reconstruction=ReconstructionMeta(source="spaced_ocr", expected_primary_rows=3),
    )
    detection = BankStyleDetector().detect(ctx)
    assert detection.primary_style == "signed_amount"
