import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from docmirror.input.extraction.page_splitter import (
    DocumentSpreadPlan,
    PageSplitDecision,
    SpreadAnalysis,
    analyze_spread_candidates,
    build_document_plan,
    confirm_document_plan_rotation,
    decision_from_analyses,
    split_or_passthrough,
)


def _spread_image(*, blank_right: bool = False):
    image = np.full((600, 840, 3), 255, dtype=np.uint8)
    for page_index, x_offset in enumerate((0, 420)):
        if blank_right and page_index == 1:
            continue
        cv2.rectangle(image, (x_offset + 24, 22), (x_offset + 396, 575), (20, 20, 20), 2)
        for row in range(8):
            y = 70 + row * 52
            cv2.line(image, (x_offset + 54, y), (x_offset + 360, y), (30, 30, 30), 3)
    return image


def _apply(matrix, x, y):
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2],
    )


def test_rotated_spread_produces_strong_90_or_270_candidate():
    upright = _spread_image()
    source = cv2.rotate(upright, cv2.ROTATE_90_COUNTERCLOCKWISE)

    analyses = analyze_spread_candidates(source)
    best = max(analyses, key=lambda item: item.score)
    decision = decision_from_analyses(analyses, mode="auto")

    assert best.rotation in {90, 270}
    assert best.score >= 0.78
    assert decision.should_split is True
    assert set(decision.rotation_candidates).issubset({90, 270})


def test_split_returns_two_portrait_slices_with_invertible_coordinates():
    upright = _spread_image()
    analyses = analyze_spread_candidates(cv2.rotate(upright, cv2.ROTATE_90_COUNTERCLOCKWISE))
    decision = decision_from_analyses(analyses, mode="auto")

    slices = split_or_passthrough(
        upright,
        source_width=600.0,
        source_height=840.0,
        selected_rotation=90,
        zoom=1.0,
        decision=decision,
        mode="auto",
    )

    assert len(slices) == 2
    assert all(page.width < page.height for page in slices)
    for page in slices:
        source_point = _apply(page.logical_to_source, 50.0, 80.0)
        roundtrip = _apply(page.source_to_logical, *source_point)
        assert roundtrip == pytest.approx((50.0, 80.0), abs=1e-6)


def test_blank_second_half_is_discarded_but_plan_counts_one_page():
    upright = _spread_image(blank_right=True)
    source = cv2.rotate(upright, cv2.ROTATE_90_COUNTERCLOCKWISE)
    analyses = analyze_spread_candidates(source)
    decision = decision_from_analyses(analyses, mode="auto")
    plan = build_document_plan({1: analyses}, source_page_numbers=[1], mode="auto")

    slices = split_or_passthrough(
        upright,
        source_width=600.0,
        source_height=840.0,
        selected_rotation=90,
        zoom=1.0,
        decision=decision,
        mode="auto",
    )

    assert decision.should_split is True
    assert decision.expected_nonblank_segments == 1
    assert plan.logical_page_count == 1
    assert len(slices) == 1


def test_page_split_off_preserves_physical_numbering():
    analyses = analyze_spread_candidates(_spread_image())
    plan = build_document_plan(
        {1: analyses, 2: analyses},
        source_page_numbers=[1, 2],
        mode="off",
    )

    assert plan.logical_starts == {1: 1, 2: 2}
    assert plan.logical_page_count == 2
    assert plan.decision_for(1).should_split is False


def test_sideways_candidate_requires_document_orientation_confirmation():
    analysis = SpreadAnalysis(
        rotation=90,
        split_position=300,
        split_ratio=0.5,
        score=0.96,
        gutter_density=0.001,
        left_density=0.08,
        right_density=0.08,
        left_aspect=0.707,
        right_aspect=0.707,
    )
    decision = PageSplitDecision(
        should_split=True,
        rotation_candidates=(90, 270),
        confidence=0.96,
        split_ratio=0.5,
        expected_nonblank_segments=2,
        analyses=(analysis,),
    )
    provisional = DocumentSpreadPlan(
        mode="auto",
        decisions={1: decision},
        logical_starts={1: 1, 2: 3},
        logical_page_count=3,
        confidence=0.96,
    )

    upright = confirm_document_plan_rotation(
        provisional,
        source_page_numbers=[1, 2],
        preferred_rotation=None,
    )
    sideways = confirm_document_plan_rotation(
        provisional,
        source_page_numbers=[1, 2],
        preferred_rotation=270,
    )

    assert upright.logical_starts == {1: 1, 2: 2}
    assert upright.logical_page_count == 2
    assert upright.decision_for(1).should_split is False
    assert sideways.logical_starts == {1: 1, 2: 3}
    assert sideways.logical_page_count == 3
    assert sideways.decision_for(1).should_split is True
