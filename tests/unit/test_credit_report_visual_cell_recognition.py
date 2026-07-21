# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from docmirror.ocr.micro_grid.cell_recognition import (
    extract_micro_cell_glyph_template,
    normalize_allowlist_text,
    recognize_micro_cell_from_image,
)
from docmirror.ocr.micro_grid.reconstruct import equal_col_bands
from docmirror.plugins.credit_report.repayment_grid import _visual_month_col_bands


class _EmptyEngine:
    def force_recognize_regions(self, *_args, **_kwargs):
        return []


def _cell_image(character: str, *, noise: bool = False):
    image = np.full((180, 240, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (30, 35), (210, 145), (0, 0, 0), 2)
    if character == "*":
        centre = (120, 90)
        for endpoint in ((120, 70), (120, 110), (101, 79), (139, 101), (101, 101), (139, 79)):
            cv2.line(image, centre, endpoint, (0, 0, 0), 4)
    else:
        cv2.putText(image, character, (96, 111), cv2.FONT_HERSHEY_SIMPLEX, 1.7, (0, 0, 0), 4)
    if noise:
        cv2.line(image, (75, 125), (170, 55), (150, 150, 150), 2)
    return image


def test_status_allowlist_preserves_hash_semantics():
    assert normalize_allowlist_text("#", {"#", "*"}, max_chars=1) == "#"


def test_cell_shape_recognizes_star_without_ocr(monkeypatch):
    import docmirror.ocr.vision.rapidocr_engine as rapidocr_engine

    monkeypatch.setattr(rapidocr_engine, "get_ocr_engine", lambda: _EmptyEngine())
    image = _cell_image("*")
    result = recognize_micro_cell_from_image(
        image,
        (30, 35, 210, 145),
        page_width=240,
        page_height=180,
        allowed_charset={"*", "N", "1", "2"},
        max_chars=1,
    )
    assert result.text == "*"
    assert result.source == "cell_crop_consensus"


def test_document_template_and_shape_recognize_noisy_n(monkeypatch):
    import docmirror.ocr.vision.rapidocr_engine as rapidocr_engine

    monkeypatch.setattr(rapidocr_engine, "get_ocr_engine", lambda: _EmptyEngine())
    reference_image = _cell_image("N")
    reference = extract_micro_cell_glyph_template(
        reference_image,
        (30, 35, 210, 145),
        page_width=240,
        page_height=180,
    )
    result = recognize_micro_cell_from_image(
        _cell_image("N", noise=True),
        (30, 35, 210, 145),
        page_width=240,
        page_height=180,
        allowed_charset={"*", "N", "1", "2"},
        max_chars=1,
        reference_templates={"N": [reference]},
    )
    assert result.text == "N"


def test_visual_month_geometry_uses_table_rules_not_header_text_bbox():
    image = np.full((120, 340, 3), 255, dtype=np.uint8)
    for x in range(40, 281, 20):
        cv2.line(image, (x, 15), (x, 105), (0, 0, 0), 2)
    legacy = equal_col_bands((55, 20, 295, 30), count=12, start_index=1, role="month")

    refined, audit = _visual_month_col_bands(
        legacy,
        page_image=image,
        page_width=340,
        page_height=120,
        y0=15,
        y1=105,
    )

    assert audit["source"] == "vertical_rule_projection"
    assert refined[0]["bbox"][0] == pytest.approx(40, abs=2)
    assert refined[-1]["bbox"][2] == pytest.approx(280, abs=2)
