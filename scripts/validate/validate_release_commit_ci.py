#!/usr/bin/env python3
"""Verify that the exact release commit has a successful main CI run."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def evaluate_release_commit_ci(runs: list[dict[str, Any]], head_sha: str) -> list[str]:
    """Require completed, successful main CI for the exact release commit."""
    matching = [run for run in runs if run.get("head_sha") == head_sha]
    if not matching:
        return [f"no completed main CI run found for release commit {head_sha}"]

    failures = [run for run in matching if run.get("conclusion") != "success"]
    return [
        f"release commit main CI concluded {run.get('conclusion') or 'unknown'} ({run.get('html_url') or 'no URL'})"
        for run in failures
    ]


def fetch_main_ci_runs(*, token: str, repository: str) -> list[dict[str, Any]]:
    """Fetch recent completed main CI runs from GitHub Actions."""
    workflow = urllib.parse.quote("ci.yml", safe="")
    query = urllib.parse.urlencode(
        {
            "branch": "main",
            "status": "completed",
            "per_page": 100,
        }
    )
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/actions/workflows/{workflow}/runs?{query}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "DocMirror-release-commit-gate",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return list(payload.get("workflow_runs") or [])


def main() -> int:
    token = os.getenv("GITHUB_TOKEN", "")
    repository = os.getenv("GITHUB_REPOSITORY", "")
    head_sha = os.getenv("GITHUB_SHA", "")
    if not token or not repository or not head_sha:
        print("GITHUB_TOKEN, GITHUB_REPOSITORY, and GITHUB_SHA are required", file=sys.stderr)
        return 2

    try:
        runs = fetch_main_ci_runs(token=token, repository=repository)
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        print(f"Unable to query GitHub Actions runs: {exc}", file=sys.stderr)
        return 2

    errors = evaluate_release_commit_ci(runs, head_sha)
    if errors:
        print("Release-commit CI validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Release commit {head_sha} has successful main CI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
