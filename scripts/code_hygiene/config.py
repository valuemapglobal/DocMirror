# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Paths and allowlists for the hygiene audit program."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCMIRROR = ROOT / "docmirror"
SCRIPTS = ROOT / "scripts"
TOOLS = ROOT / "tools"
TESTS = ROOT / "tests"
CONFIGS_YAML = ROOT / "docmirror" / "configs" / "yaml"
ALLOWLIST_PATH = ROOT / "configs" / "hygiene" / "allowlist.yaml"

# Package roots scanned for orphan modules and import graph.
SCAN_PACKAGE_DIRS = (DOCMIRROR,)

# Additional trees for ruff / commented-code passes.
RUFF_TARGETS = ("docmirror", "scripts", "tools")

# Modules that are legitimate entry points (never flagged as orphan).
ENTRY_MODULE_SUFFIXES = (
    "__main__",
    "__init__",
    "conftest",
)

ENTRY_MODULE_PATHS = {
    "docmirror.__main__",
    "docmirror.cli.main",
    "docmirror.server.api",
}

# Paths always excluded from orphan / vulture scans.
EXCLUDE_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".git",
        ".venv",
        "node_modules",
        "_archive",
        ".pytest_cache",
        "site-packages",
    }
)

# Orphan scan skips modules under archive/legacy trees (not audited as orphans).
ORPHAN_EXCLUDE_PATH_PARTS = ("_archive", "legacy", "compat", "deprecated")

# Ruff rule set for strict hygiene pass (separate from default pyproject profile).
RUFF_HYGIENE_SELECT = (
    "F401",  # unused import
    "F841",  # unused variable
    "ARG001",  # unused function argument
    "ARG002",  # unused method argument
    "ARG005",  # unused lambda argument
    "ERA001",  # commented-out code
    "UP",  # pyupgrade / deprecated syntax
)

# Per-file ruff ignores for known false positives (path suffix → rule codes).
RUFF_PER_FILE_IGNORES: dict[str, tuple[str, ...]] = {
    "**/__init__.py": ("F401", "F811"),
}
