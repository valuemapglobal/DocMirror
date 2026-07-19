# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the 14-day main CI release gate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scripts.validate.validate_ci_green_window import evaluate_green_window, required_complete_days

NOW = datetime(2026, 8, 3, 12, tzinfo=UTC)


def _run(day_offset: int, conclusion: str = "success") -> dict[str, str]:
    created_at = NOW - timedelta(days=day_offset)
    return {
        "created_at": created_at.isoformat(),
        "status": "completed",
        "conclusion": conclusion,
        "html_url": f"https://github.example/runs/{day_offset}/{conclusion}",
    }


def test_required_days_exclude_the_incomplete_current_utc_day():
    days = required_complete_days(NOW, 14)
    assert len(days) == 14
    assert days[0].isoformat() == "2026-07-20"
    assert days[-1].isoformat() == "2026-08-02"


def test_green_window_accepts_one_successful_run_per_complete_day():
    errors, by_day = evaluate_green_window([_run(offset) for offset in range(1, 15)], now=NOW, min_days=14)
    assert errors == []
    assert len(by_day) == 14


def test_green_window_rejects_a_missing_day():
    errors, _ = evaluate_green_window([_run(offset) for offset in range(1, 14)], now=NOW, min_days=14)
    assert errors == ["2026-07-20: no completed main CI run"]


def test_green_window_rejects_a_failure_even_if_same_day_has_a_success():
    runs = [_run(offset) for offset in range(1, 15)]
    runs.append(_run(7, "failure"))
    errors, _ = evaluate_green_window(runs, now=NOW, min_days=14)
    assert len(errors) == 1
    assert "2026-07-27: non-green main CI run(s): failure" in errors[0]


def test_green_window_ignores_current_day_and_incomplete_runs():
    runs = [_run(offset) for offset in range(1, 15)]
    runs.extend(
        [
            _run(0, "failure"),
            {
                "created_at": _run(3)["created_at"],
                "status": "in_progress",
                "conclusion": "failure",
                "html_url": "https://github.example/runs/in-progress",
            },
        ]
    )
    errors, _ = evaluate_green_window(runs, now=NOW, min_days=14)
    assert errors == []
