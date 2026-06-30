# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DRC Artifact Stream — page/chunk intermediate artifact writer and finalizer.

GA 1.0 §6.8: Intermediate artifacts (page mirror fragments, chunks, edition
partials) must be written atomically so that successful work is never lost,
even when subsequent work units fail. The finalizer merges partial artifacts
into the contract output files.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Default size guards per cost profile ───────────────────────────────
PROFILE_SIZE_GUARDS: dict[str, int] = {
    "compact": 20 * 1024 * 1024,  #  20 MB
    "full": 100 * 1024 * 1024,  # 100 MB
    "forensic": 500 * 1024 * 1024,  # 500 MB
}


class IntermediateArtifactWriter:
    """Writes intermediate page/chunk artifacts atomically to task dir.

    Directory layout under task_dir/intermediate/:
        pages/
          001/
            page_0001.mirror_fragment.json
            page_0001.quality.json
        chunks/
          001/
            chunk_0001.json
        markdown/
          001/
            page_0001.md
        projections/
          001/
            community.partial.json
    """

    def __init__(
        self,
        task_dir: Path,
        *,
        profile: str = "full",
    ) -> None:
        self._task_dir = Path(task_dir)
        self._intermediate_dir = self._task_dir / "intermediate"
        self._profile = profile
        self._size_guard = PROFILE_SIZE_GUARDS.get(profile, PROFILE_SIZE_GUARDS["full"])
        self._total_bytes_written = 0

    @property
    def intermediate_dir(self) -> Path:
        return self._intermediate_dir

    # ── Page artifacts ─────────────────────────────────────────────

    def write_page_mirror_fragment(
        self,
        file_id: str,
        page_number: int,
        data: dict[str, Any],
    ) -> Path:
        """Write a single-page mirror fragment atomically."""
        dest = self._intermediate_dir / "pages" / file_id / f"page_{page_number:04d}.mirror_fragment.json"
        path = _atomic_write_json(dest, data)
        self._track_size(path)
        return path

    def write_page_quality(
        self,
        file_id: str,
        page_number: int,
        data: dict[str, Any],
    ) -> Path:
        """Write per-page quality data."""
        dest = self._intermediate_dir / "pages" / file_id / f"page_{page_number:04d}.quality.json"
        path = _atomic_write_json(dest, data)
        self._track_size(path)
        return path

    def read_page_fragments(self, file_id: str) -> list[dict[str, Any]]:
        """Read all page mirror fragments for a file, sorted by page."""
        frag_dir = self._intermediate_dir / "pages" / file_id
        return _read_sorted_json_files(frag_dir, "page_*.mirror_fragment.json")

    # ── Chunk artifacts ────────────────────────────────────────────

    def write_chunk(
        self,
        file_id: str,
        chunk_index: int,
        data: dict[str, Any],
    ) -> Path:
        """Write a single RAG chunk fragment."""
        dest = self._intermediate_dir / "chunks" / file_id / f"chunk_{chunk_index:04d}.json"
        path = _atomic_write_json(dest, data)
        self._track_size(path)
        return path

    def read_chunks(self, file_id: str) -> list[dict[str, Any]]:
        """Read all chunk fragments for a file, sorted."""
        chunk_dir = self._intermediate_dir / "chunks" / file_id
        return _read_sorted_json_files(chunk_dir, "chunk_*.json")

    # ── Markdown page fragments ────────────────────────────────────

    def write_page_markdown(
        self,
        file_id: str,
        page_number: int,
        markdown: str,
    ) -> Path:
        """Write per-page markdown fragment."""
        dest = self._intermediate_dir / "markdown" / file_id / f"page_{page_number:04d}.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(markdown, encoding="utf-8")
        self._track_size(dest)
        return dest

    # ── Projection partials ────────────────────────────────────────

    def write_projection_partial(
        self,
        file_id: str,
        edition: str,
        data: dict[str, Any],
    ) -> Path:
        """Write a partial edition projection."""
        dest = self._intermediate_dir / "projections" / file_id / f"{edition}.partial.json"
        path = _atomic_write_json(dest, data)
        self._track_size(path)
        return path

    # ── Size guard ─────────────────────────────────────────────────

    def check_size_guard(self) -> dict[str, Any]:
        """Return current size status and warn if over budget."""
        over = self._total_bytes_written > self._size_guard
        if over:
            logger.warning(
                "Intermediate artifact size (%s bytes) exceeds %s profile guard (%s bytes)",
                self._total_bytes_written,
                self._profile,
                self._size_guard,
            )
        return {
            "profile": self._profile,
            "size_guard_bytes": self._size_guard,
            "total_bytes_written": self._total_bytes_written,
            "over_budget": over,
        }

    def _track_size(self, path: Path) -> None:
        if path.is_file():
            self._total_bytes_written += path.stat().st_size


class ArtifactFinalizer:
    """Merges intermediate artifacts into final contract outputs.

    GA 1.0 §6.8: The finalizer ensures that final Mirror / Markdown / Edition
    outputs are reconstructible from intermediate fragments, and that each
    fragment's digest is recorded for consistency verification.
    """

    def __init__(self, writer: IntermediateArtifactWriter) -> None:
        self._writer = writer

    def merge_page_fragments_to_mirror(
        self,
        file_id: str,
        *,
        document_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Merge all page mirror fragments into a single Mirror dict."""
        fragments = self._writer.read_page_fragments(file_id)
        pages: list[dict[str, Any]] = []
        full_text_parts: list[str] = []

        for frag in fragments:
            pages.append(frag.get("page", {}))
            full_text_parts.append(frag.get("full_text", ""))

        mirror: dict[str, Any] = {
            "document": document_metadata or {},
            "pages": pages,
            "full_text": "\n\n".join(full_text_parts),
            "_fragments_digest": _compute_fragments_digest(fragments),
        }
        return mirror

    def merge_chunks(self, file_id: str) -> list[dict[str, Any]]:
        """Collect all chunk fragments into a sorted list."""
        return self._writer.read_chunks(file_id)

    def merge_projection(
        self,
        file_id: str,
        edition: str,
    ) -> dict[str, Any] | None:
        """Read a partial projection if it exists."""
        partial_path = self._writer.intermediate_dir / "projections" / file_id / f"{edition}.partial.json"
        if partial_path.is_file():
            try:
                return json.loads(partial_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
        return None

    def build_merge_manifest(self, file_id: str) -> dict[str, Any]:
        """Build a merge manifest describing all fragments used."""
        fragments = self._writer.read_page_fragments(file_id)
        chunks = self._writer.read_chunks(file_id)
        return {
            "file_id": file_id,
            "page_fragment_count": len(fragments),
            "chunk_count": len(chunks),
            "page_fragments_digest": _compute_fragments_digest(fragments),
            "chunks_digest": _compute_fragments_digest(chunks),
        }


def _atomic_write_json(path: Path, data: dict[str, Any]) -> Path:
    """Write JSON atomically with temp + rename. Returns final path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix="." + path.name + ".",
    )
    try:
        content = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        os.write(tmp_fd, content.encode("utf-8"))
        os.fsync(tmp_fd)
    finally:
        os.close(tmp_fd)
    os.replace(tmp_name, str(path))
    return path


def _read_sorted_json_files(directory: Path, pattern: str) -> list[dict[str, Any]]:
    """Read JSON files matching a glob, sorted by name."""
    if not directory.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for fpath in sorted(directory.glob(pattern)):
        try:
            results.append(json.loads(fpath.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return results


def _compute_fragments_digest(fragments: list[dict[str, Any]]) -> str:
    """Compute SHA-256 over serialized fragments for consistency checks."""
    serialized = json.dumps(fragments, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


__all__ = [
    "ArtifactFinalizer",
    "IntermediateArtifactWriter",
]
