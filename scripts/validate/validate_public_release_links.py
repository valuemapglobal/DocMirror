#!/usr/bin/env python3
"""Reject stale or misleading URLs on DocMirror's public release surfaces."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PUBLIC_ROOT_FILES = (
    "README.md",
    "README_zh-CN.md",
    "CONTRIBUTING.md",
    "mkdocs.yml",
    "pyproject.toml",
    "scripts/generate_openapi.py",
    "tests/README.md",
)
PUBLIC_ROOT_DIRS = ("docs", "docmirror", "sdks")
TEXT_SUFFIXES = {
    ".go",
    ".java",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".ts",
    ".xml",
    ".yaml",
    ".yml",
}
SKIP_DIR_NAMES = {".git", "__pycache__", "dist", "node_modules", "target"}

FORBIDDEN_URLS = (
    (
        "unavailable docmirror.dev/docmirror.com host",
        re.compile(r"https?://(?:(?:api|docs)\.)?docmirror\.(?:dev|com)(?=[/:?#'\"<>\s]|$)"),
    ),
    (
        "unavailable docmirror.valuemapglobal.com host",
        re.compile(r"https?://docmirror\.valuemapglobal\.com(?=[/:?#'\"<>\s]|$)"),
    ),
    (
        "wrong-case GitHub Pages path",
        re.compile(r"valuemapglobal\.github\.io/docmirror(?=[/#?'\"<>\s]|$)"),
    ),
    (
        "wrong-case canonical GitHub repository path",
        re.compile(r"github\.com/valuemapglobal/docmirror(?=(?:\.git)?[/#?'\"<>\s]|$)"),
    ),
    (
        "nonexistent standalone Go SDK repository",
        re.compile(r"github\.com/valuemapglobal/docmirror-go-sdk(?=[/@#?'\"<>\s]|$)"),
    ),
)

REQUIRED_SNIPPETS = {
    "mkdocs.yml": (
        "site_url: https://valuemapglobal.github.io/DocMirror/",
        "repo_url: https://github.com/valuemapglobal/DocMirror",
    ),
    "pyproject.toml": (
        'Homepage = "https://valuemapglobal.github.io/DocMirror/"',
        'Documentation = "https://valuemapglobal.github.io/DocMirror/"',
        'Repository = "https://github.com/valuemapglobal/DocMirror"',
    ),
    "sdks/typescript/README.md": ("Preview status:", "not published to npm"),
    "sdks/go/README.md": ("Preview status:", "no released module version to install yet"),
    "sdks/go/go.mod": ("module github.com/valuemapglobal/DocMirror/sdks/go",),
    "sdks/java/README.md": ("Preview status:", "not published to", "Maven Central"),
    "sdks/mcp-server/README.md": ("Preview status:", "not published to npm"),
    "sdks/mcp-server/PUBLISH.md": ("Publishing @docmirror/mcp-server to npm (Blocked)",),
}


def _iter_public_files(root: Path):
    for relative in PUBLIC_ROOT_FILES:
        path = root / relative
        if path.is_file():
            yield path
    for relative in PUBLIC_ROOT_DIRS:
        directory = root / relative
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if any(part in SKIP_DIR_NAMES for part in path.relative_to(root).parts):
                continue
            yield path


def find_issues(root: Path = REPO_ROOT) -> list[str]:
    """Return human-readable violations for public release files."""
    issues: list[str] = []
    seen: set[Path] = set()
    for path in _iter_public_files(root):
        if path in seen:
            continue
        seen.add(path)
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for description, pattern in FORBIDDEN_URLS:
                if pattern.search(line):
                    issues.append(f"{relative}:{lineno}: {description}")

    for relative, snippets in REQUIRED_SNIPPETS.items():
        path = root / relative
        if not path.is_file():
            issues.append(f"{relative}: required public release file is missing")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for snippet in snippets:
            if snippet not in text:
                issues.append(f"{relative}: missing required marker: {snippet!r}")

    return issues


def main() -> int:
    issues = find_issues()
    if issues:
        print("Public release surface validation failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("Public release surface validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
