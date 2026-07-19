# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for trustworthy public release links and preview claims."""

from scripts.validate.validate_public_release_links import REPO_ROOT, find_issues


def test_public_release_surfaces_do_not_advertise_unavailable_endpoints():
    assert find_issues(REPO_ROOT) == []
