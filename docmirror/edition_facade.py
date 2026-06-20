# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Non-Core facade for edition projection orchestration."""

from __future__ import annotations

from typing import Any


def build_edition_projections(*args: Any, **kwargs: Any) -> dict[str, dict[str, Any] | None]:
    from docmirror.server.output_builder import build_all_projections

    return build_all_projections(*args, **kwargs)


__all__ = ["build_edition_projections"]
