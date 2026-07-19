#!/usr/bin/env python3
"""Verify that main CI was successful on every complete UTC day in a window."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_WORKFLOW = "ci.yml"
DEFAULT_BRANCH = "main"


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def required_complete_days(now: datetime, min_days: int) -> tuple[date, ...]:
    """Return the previous ``min_days`` complete UTC calendar days."""
    if min_days < 1:
        raise ValueError("min_days must be at least 1")
    utc_now = now.astimezone(UTC)
    end = utc_now.date() - timedelta(days=1)
    start = end - timedelta(days=min_days - 1)
    return tuple(start + timedelta(days=offset) for offset in range(min_days))


def evaluate_green_window(
    runs: list[dict[str, Any]],
    *,
    now: datetime,
    min_days: int,
) -> tuple[list[str], dict[date, list[dict[str, Any]]]]:
    """Evaluate daily coverage and reject every non-successful completed run."""
    required = required_complete_days(now, min_days)
    required_set = set(required)
    by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)

    for run in runs:
        created_at = run.get("created_at")
        if not isinstance(created_at, str) or run.get("status") != "completed":
            continue
        run_day = _parse_timestamp(created_at).date()
        if run_day in required_set:
            by_day[run_day].append(run)

    errors: list[str] = []
    for day in required:
        daily_runs = by_day.get(day, [])
        if not daily_runs:
            errors.append(f"{day.isoformat()}: no completed main CI run")
            continue
        failures = [run for run in daily_runs if run.get("conclusion") != "success"]
        if failures:
            details = ", ".join(
                f"{run.get('conclusion') or 'unknown'} ({run.get('html_url') or 'no URL'})" for run in failures
            )
            errors.append(f"{day.isoformat()}: non-green main CI run(s): {details}")

    return errors, dict(by_day)


def fetch_workflow_runs(
    *,
    token: str,
    repository: str,
    workflow: str,
    branch: str,
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    """Fetch completed workflow runs from the GitHub Actions REST API."""
    workflow_path = urllib.parse.quote(workflow, safe="")
    endpoint = f"https://api.github.com/repos/{repository}/actions/workflows/{workflow_path}/runs"
    runs: list[dict[str, Any]] = []

    for page in range(1, 11):
        query = urllib.parse.urlencode(
            {
                "branch": branch,
                "status": "completed",
                "created": f"{start.isoformat()}..{end.isoformat()}",
                "per_page": 100,
                "page": page,
            }
        )
        request = urllib.request.Request(
            f"{endpoint}?{query}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "DocMirror-release-gate",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        page_runs = payload.get("workflow_runs") or []
        runs.extend(page_runs)
        if len(page_runs) < 100:
            break

    return runs


def _write_step_summary(message: str) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with Path(summary_path).open("a", encoding="utf-8") as summary:
        summary.write(message + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-days", type=int, default=14)
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    args = parser.parse_args(argv)

    token = os.getenv("GITHUB_TOKEN", "")
    if not token or not args.repository:
        print("GITHUB_TOKEN and GITHUB_REPOSITORY are required", file=sys.stderr)
        return 2

    days = required_complete_days(datetime.now(UTC), args.min_days)
    try:
        runs = fetch_workflow_runs(
            token=token,
            repository=args.repository,
            workflow=args.workflow,
            branch=args.branch,
            start=days[0],
            end=days[-1],
        )
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        print(f"Unable to query GitHub Actions runs: {exc}", file=sys.stderr)
        return 2

    errors, by_day = evaluate_green_window(runs, now=datetime.now(UTC), min_days=args.min_days)
    window = f"{days[0].isoformat()} through {days[-1].isoformat()}"
    if errors:
        print(f"{args.min_days}-day main CI green-window validation failed ({window}):")
        for error in errors:
            print(f"- {error}")
        _write_step_summary(
            f"## ❌ Main CI green window failed\n\nWindow: {window}\n\n" + "\n".join(f"- {e}" for e in errors)
        )
        return 1

    run_count = sum(len(day_runs) for day_runs in by_day.values())
    message = f"{args.min_days}-day main CI green window passed ({window}; {run_count} completed run(s))."
    print(message)
    _write_step_summary(f"## ✅ Main CI green window passed\n\n{message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
