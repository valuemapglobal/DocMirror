# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from scripts.validate.validate_release_commit_ci import evaluate_release_commit_ci


def test_release_commit_ci_requires_matching_run():
    assert evaluate_release_commit_ci([], "abc") == ["no completed main CI run found for release commit abc"]


def test_release_commit_ci_accepts_successful_matching_run():
    runs = [{"head_sha": "abc", "conclusion": "success", "html_url": "https://example.test/run"}]
    assert evaluate_release_commit_ci(runs, "abc") == []


def test_release_commit_ci_rejects_failed_matching_run():
    runs = [{"head_sha": "abc", "conclusion": "failure", "html_url": "https://example.test/run"}]
    assert evaluate_release_commit_ci(runs, "abc") == [
        "release commit main CI concluded failure (https://example.test/run)"
    ]
