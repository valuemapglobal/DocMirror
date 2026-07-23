# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
DTI (Document Type Identity) validators — design 09 §4.3.

Validates that ``business_scene`` strings used in plugins, middleware, and API
responses exist in the SSOT keyword corpus loaded from plugin resources.

Functions::

    load_business_scenes()       Frozenset of all valid scene keys
    validate_business_scene()    True for known scenes (and sentinel values)
    validate_business_scenes()   Return list of unknown scenes from an iterable
    assert_business_scene()      Raise ``ValueError`` for unknown scenes

Sentinel values ``unknown``, ``generic``, and empty string always pass validation.
Use ``assert_business_scene`` at plugin registration or config authoring time
to catch typos before they reach production classification.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache


@lru_cache(maxsize=1)
def load_business_scenes() -> frozenset[str]:
    """Return all valid ``business_scene`` keys from plugin resources."""
    from docmirror.configs.scene.loader import get_scene_specs

    return frozenset(get_scene_specs())


def validate_business_scene(scene: str) -> bool:
    """True if ``scene`` is a known business_scene (120-class SSOT)."""
    if not scene or scene in ("unknown", "generic", ""):
        return True
    return scene in load_business_scenes()


def validate_business_scenes(scenes: Iterable[str]) -> list[str]:
    """Return unknown scenes (empty list = all valid)."""
    known = load_business_scenes()
    if not known:
        return []
    unknown: list[str] = []
    for scene in scenes:
        if not scene or scene in ("unknown", "generic"):
            continue
        if scene not in known:
            unknown.append(scene)
    return unknown


def assert_business_scene(scene: str) -> None:
    """Raise ValueError if scene is not in SSOT."""
    if not validate_business_scene(scene):
        raise ValueError(f"Unknown business_scene {scene!r}; add it to a plugin scene_keywords resource")
