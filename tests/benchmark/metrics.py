"""Small dependency-free benchmark metrics."""

from __future__ import annotations

from typing import Any


def compute_cer(prediction: str, ground_truth: str) -> float:
    if not ground_truth:
        return 0.0 if not prediction else 1.0
    return _edit_distance(prediction, ground_truth) / len(ground_truth)


def compute_teds(prediction: list[list[Any]], ground_truth: list[list[Any]]) -> float:
    pred_cells = [str(cell) for row in prediction for cell in row]
    gt_cells = [str(cell) for row in ground_truth for cell in row]
    if not gt_cells:
        return 1.0 if not pred_cells else 0.0
    distance = _edit_distance("|".join(pred_cells), "|".join(gt_cells))
    denom = max(1, len("|".join(gt_cells)))
    return max(0.0, min(1.0, 1.0 - distance / denom))


def compute_reading_order_accuracy(prediction: list[int], ground_truth: list[int]) -> float:
    if prediction == ground_truth:
        return 1.0
    if list(reversed(prediction)) == ground_truth:
        return 0.0
    if not ground_truth:
        return 1.0 if not prediction else 0.0
    matches = sum(1 for left, right in zip(prediction, ground_truth, strict=False) if left == right)
    return matches / len(ground_truth)


def _edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[j - 1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]
