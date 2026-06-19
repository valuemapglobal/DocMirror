#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deprecated entrypoint — use tools/compat/fold_mirror_to_page_canvas.py."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.compat.fold_mirror_to_page_canvas import main

if __name__ == "__main__":
    raise SystemExit(main())
