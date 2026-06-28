from docmirror.structure.ocr.micro_grid.models import OCRToken
from docmirror.structure.ocr.micro_grid.reconstruct import (
    assign_tokens,
    assign_tokens_to_col_bands,
    build_cell,
    dedupe_visual_tokens,
    expand_tokens_to_char_tokens,
)


def _row():
    return {"index": 0, "bbox": [0, 0, 100, 20]}


def _col():
    return {"index": 1, "bbox": [10, 0, 20, 20]}


def test_assign_tokens_uses_bbox_overlap_not_only_center_inside():
    token = OCRToken(
        token_id="wide_n",
        text="N",
        bbox=(5, 2, 21, 18),
        confidence=0.9,
        page=1,
        source="native_test",
    )

    assigned = assign_tokens([token], _row(), _col())

    assert [token.token_id for token in assigned] == ["wide_n"]
    cell = build_cell(row_band=_row(), col_band=_col(), tokens=assigned, text="N", role="status")
    assert cell.assignment_method == "overlap:native_token"
    assert cell.assignment_confidence > 0.7


def test_dedupe_visual_tokens_prefers_ocr_char_split_over_line_fallback():
    original = OCRToken(
        token_id="ocr_word",
        text="NN",
        bbox=(10, 0, 30, 20),
        confidence=0.93,
        page=1,
        source="rapidocr",
    )
    ocr_chars = expand_tokens_to_char_tokens([original])
    fallback = OCRToken(
        token_id="line_0_0",
        text="N",
        bbox=(10.2, 0, 20.2, 20),
        confidence=0.99,
        page=1,
        source="ocr_line_split",
    )

    deduped = dedupe_visual_tokens([*ocr_chars, fallback])

    assert [token.text for token in deduped] == ["N", "N"]
    assert "line_0_0" not in {token.token_id for token in deduped}
    assert {token.source_token_id for token in deduped} == {"ocr_word"}


def test_row_assignment_gives_each_token_to_one_best_cell_only():
    row = {"index": 0, "bbox": [0, 0, 100, 20]}
    cols = [
        {"index": 1, "bbox": [10, 0, 20, 20]},
        {"index": 2, "bbox": [20, 0, 30, 20]},
    ]
    token = OCRToken(
        token_id="wide_boundary",
        text="0",
        bbox=(18, 0, 24, 20),
        confidence=0.9,
        page=1,
        source="rapidocr_char_split",
    )

    assigned = assign_tokens_to_col_bands([token], row, cols)

    assert assigned[1] == []
    assert [t.token_id for t in assigned[2]] == ["wide_boundary"]
