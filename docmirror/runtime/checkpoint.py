# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DRC Checkpoint Ledger — checkpoint path, fingerprint, resume validation.

GA 1.0 §6.4: Checkpoints allow tasks to be safely resumed after interruption.
Each checkpoint carries input_digest, parse_control_fingerprint, and
runtime_profile_fingerprint to prevent stale artifact reuse.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class CheckpointManager:
    """Manages checkpoint persistence under task_dir/checkpoints/.

    Directory layout:
        checkpoints/
          input/
            001.source
            001.digest.json
          pages/
            001/page_0001.mirror_fragment.json
            001/page_0001.quality.json
          chunks/
            001/chunk_0001.json
          projections/
            001/community.partial.json
    """

    def __init__(
        self,
        task_dir: Path,
        *,
        input_digest: str = "",
        parse_control_fingerprint: str = "",
        runtime_profile_fingerprint: str = "",
    ) -> None:
        self._task_dir = Path(task_dir)
        self._checkpoints_dir = self._task_dir / "checkpoints"
        self._input_digest = input_digest
        self._parse_control_fingerprint = parse_control_fingerprint
        self._runtime_profile_fingerprint = runtime_profile_fingerprint

    @property
    def checkpoints_dir(self) -> Path:
        return self._checkpoints_dir

    def fingerprint(self) -> str:
        """Composite fingerprint of input + parse control + runtime profile."""
        data = json.dumps(
            {
                "input_digest": self._input_digest,
                "parse_control": self._parse_control_fingerprint,
                "runtime_profile": self._runtime_profile_fingerprint,
            },
            sort_keys=True,
        )
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    # ── Input checkpoint ───────────────────────────────────────────

    def save_input_source(self, file_id: str, source_path: Path) -> Path:
        """Copy input file into checkpoints/input/ for resume."""
        dest_dir = self._checkpoints_dir / "input"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{file_id}.source"
        dest.write_bytes(source_path.read_bytes())
        return dest

    def save_input_digest(self, file_id: str, digest: str) -> Path:
        """Save input digest metadata."""
        dest_dir = self._checkpoints_dir / "input"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{file_id}.digest.json"
        dest.write_text(
            json.dumps(
                {
                    "file_id": file_id,
                    "input_digest": digest,
                    "parse_control_fingerprint": self._parse_control_fingerprint,
                    "runtime_profile_fingerprint": self._runtime_profile_fingerprint,
                    "checkpoint_fingerprint": self.fingerprint(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return dest

    def validate_resume(self, file_id: str, expected_digest: str) -> bool:
        """Check whether an existing checkpoint fingerprint matches.

        Returns True when the stored fingerprint matches the current
        input_digest + control fingerprints, meaning the checkpoint is
        safe to reuse.
        """
        digest_path = self._checkpoints_dir / "input" / f"{file_id}.digest.json"
        if not digest_path.is_file():
            return False
        try:
            data = json.loads(digest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        return (
            data.get("input_digest") == expected_digest
            and data.get("parse_control_fingerprint") == self._parse_control_fingerprint
            and data.get("runtime_profile_fingerprint") == self._runtime_profile_fingerprint
        )

    # ── Page checkpoint ────────────────────────────────────────────

    def save_page_fragment(
        self,
        file_id: str,
        page_number: int,
        fragment: dict[str, Any],
    ) -> Path:
        """Save a page-level mirror fragment."""
        dest_dir = self._checkpoints_dir / "pages" / file_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"page_{page_number:04d}.mirror_fragment.json"
        _atomic_write_json(dest, fragment)
        return dest

    def save_page_quality(
        self,
        file_id: str,
        page_number: int,
        quality: dict[str, Any],
    ) -> Path:
        """Save page-level quality data."""
        dest_dir = self._checkpoints_dir / "pages" / file_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"page_{page_number:04d}.quality.json"
        _atomic_write_json(dest, quality)
        return dest

    def load_page_fragments(self, file_id: str) -> list[dict[str, Any]]:
        """Load all page fragments for a file, sorted by page number."""
        frag_dir = self._checkpoints_dir / "pages" / file_id
        if not frag_dir.is_dir():
            return []
        fragments: list[dict[str, Any]] = []
        for frag_path in sorted(frag_dir.glob("page_*.mirror_fragment.json")):
            try:
                fragments.append(json.loads(frag_path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return fragments

    def has_page_fragment(self, file_id: str, page_number: int) -> bool:
        """Check whether a specific page fragment exists."""
        frag_path = (
            self._checkpoints_dir / "pages" / file_id /
            f"page_{page_number:04d}.mirror_fragment.json"
        )
        return frag_path.is_file()

    # ── Chunk checkpoint ───────────────────────────────────────────

    def save_chunk(
        self,
        file_id: str,
        chunk_index: int,
        chunk: dict[str, Any],
    ) -> Path:
        """Save a chunk fragment."""
        dest_dir = self._checkpoints_dir / "chunks" / file_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"chunk_{chunk_index:04d}.json"
        _atomic_write_json(dest, chunk)
        return dest

    def load_chunks(self, file_id: str) -> list[dict[str, Any]]:
        """Load all chunks for a file, sorted by index."""
        chunk_dir = self._checkpoints_dir / "chunks" / file_id
        if not chunk_dir.is_dir():
            return []
        chunks: list[dict[str, Any]] = []
        for chunk_path in sorted(chunk_dir.glob("chunk_*.json")):
            try:
                chunks.append(json.loads(chunk_path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return chunks

    # ── Projection checkpoint ──────────────────────────────────────

    def save_projection_partial(
        self,
        file_id: str,
        edition: str,
        data: dict[str, Any],
    ) -> Path:
        """Save a partial projection for a specific edition."""
        dest_dir = self._checkpoints_dir / "projections" / file_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{edition}.partial.json"
        _atomic_write_json(dest, data)
        return dest


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically using temp file + rename."""
    import os
    import tempfile

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


__all__ = [
    "CheckpointManager",
]
