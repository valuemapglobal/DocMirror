# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Structure fixture bank for GA 1.0 STR-6-1.

Provides test fixtures covering:
  - multi-column layout reading order
  - header/footer detection and suppression
  - cross-page paragraph continuity
  - cross-page table merging
  - image/formula node coverage
  - relation detection (caption_of, title_of)

Fixtures are used by TQG document_structure_oracles.py for release gates.
"""

from __future__ import annotations

from typing import Any

from .fixtures import STRUCTURE_FIXTURES, FixtureSpec

__all__ = ["STRUCTURE_FIXTURES", "FixtureSpec"]
