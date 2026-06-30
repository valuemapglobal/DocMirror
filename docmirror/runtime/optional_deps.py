# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Optional dependency helpers with user-facing install guidance."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType


@dataclass(slots=True)
class FeatureUnavailableError(ImportError):
    """Raised when an optional feature dependency is missing."""

    feature: str
    missing: tuple[str, ...]
    extra: str

    @property
    def install_hint(self) -> str:
        return f"pip install 'docmirror[{self.extra}]'"

    def __str__(self) -> str:
        missing = ", ".join(self.missing)
        return f"{self.feature} requires missing optional dependency: {missing}. Install with: {self.install_hint}"


def require_optional_module(module_name: str, *, feature: str, extra: str) -> ModuleType:
    """Import an optional module or raise a DocMirror-native guidance error."""
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise FeatureUnavailableError(feature=feature, missing=(module_name,), extra=extra) from exc


def require_optional_modules(
    module_names: list[str] | tuple[str, ...], *, feature: str, extra: str
) -> dict[str, ModuleType]:
    """Import multiple optional modules or report all missing modules."""
    loaded: dict[str, ModuleType] = {}
    missing: list[str] = []
    for module_name in module_names:
        try:
            loaded[module_name] = importlib.import_module(module_name)
        except ImportError:
            missing.append(module_name)
    if missing:
        raise FeatureUnavailableError(feature=feature, missing=tuple(missing), extra=extra)
    return loaded


__all__ = ["FeatureUnavailableError", "require_optional_module", "require_optional_modules"]
