# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""File registry — CCC-1 unique file identity and fingerprint."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class FileRegistryEntry(BaseModel):
    """Immutable file registration record."""

    file_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    path: str = ""
    size: int = 0
    mime_type: str = ""
    sha256_fast: str = ""
    sha256_strict: str | None = None
    upload_time: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_channel: str = "local"
    has_text_layer: bool | None = None
    has_image_layer: bool | None = None
    page_count: int | None = None
    is_encrypted: bool | None = None
    risk_level: str = "unknown"
    extra: dict[str, Any] = Field(default_factory=dict)


class FileFingerprint(BaseModel):
    """Unified file fingerprint (L1) — CCC-1 summary for debug/UDIF."""

    file_id: str = ""
    path: str = ""
    mime_type: str = ""
    size: int = 0
    sha256_fast: str = ""
    sha256_strict: str | None = None
    page_count: int | None = None
    has_text_layer: bool | None = None
    has_image_layer: bool | None = None
    is_encrypted: bool | None = None
    risk_level: str = "unknown"
    source_channel: str = "local"

    @classmethod
    def from_registry_entry(cls, entry: FileRegistryEntry | dict[str, Any]) -> FileFingerprint:
        data = entry if isinstance(entry, dict) else entry.model_dump()
        return cls(
            file_id=str(data.get("file_id") or ""),
            path=str(data.get("path") or ""),
            mime_type=str(data.get("mime_type") or ""),
            size=int(data.get("size") or 0),
            sha256_fast=str(data.get("sha256_fast") or ""),
            sha256_strict=data.get("sha256_strict"),
            page_count=data.get("page_count"),
            has_text_layer=data.get("has_text_layer"),
            has_image_layer=data.get("has_image_layer"),
            is_encrypted=data.get("is_encrypted"),
            risk_level=str(data.get("risk_level") or "unknown"),
            source_channel=str(data.get("source_channel") or "local"),
        )


def compute_sha256_fast(path: Path) -> str:
    """Fast fingerprint: size + mtime + partial hash (matches dispatcher cache key style)."""
    stat = path.stat()
    with open(path, "rb") as f:
        head = f.read(4096)
    partial = hashlib.md5(head).hexdigest()[:8]
    return f"fast:{stat.st_size}:{stat.st_mtime}:{partial}"


def compute_sha256_strict(path: Path, chunk_size: int = 65536) -> str:
    """Full-file SHA256."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def probe_pdf_meta(path: Path, *, max_sample_pages: int = 3) -> dict[str, Any]:
    """Lightweight PDF probe for L1 fingerprint fields."""
    meta: dict[str, Any] = {}
    try:
        import fitz
    except ImportError:
        return meta
    try:
        doc = fitz.open(str(path))
    except Exception:
        return meta
    try:
        meta["page_count"] = len(doc)
        meta["is_encrypted"] = bool(getattr(doc, "is_encrypted", False))
        meta["has_image_layer"] = len(doc) > 0
        text_found = False
        for i in range(min(len(doc), max_sample_pages)):
            if doc[i].get_text().strip():
                text_found = True
                break
        meta["has_text_layer"] = text_found
    finally:
        doc.close()
    return meta


def register_file(
    path: str | Path,
    *,
    mime_type: str = "",
    source_channel: str = "local",
    strict_hash: bool = False,
    pdf_meta: dict[str, Any] | None = None,
) -> FileRegistryEntry:
    """Create a FileRegistryEntry for a local file."""
    p = Path(path)
    entry = FileRegistryEntry(
        path=str(p.resolve()),
        size=p.stat().st_size if p.exists() else 0,
        mime_type=mime_type,
        sha256_fast=compute_sha256_fast(p) if p.exists() else "",
        source_channel=source_channel,
    )
    if strict_hash and p.exists():
        entry.sha256_strict = compute_sha256_strict(p)
    pdf_meta = pdf_meta or {}
    if p.suffix.lower() == ".pdf" and p.exists() and not pdf_meta:
        pdf_meta = probe_pdf_meta(p)
    if pdf_meta:
        entry.has_text_layer = pdf_meta.get("has_text_layer")
        entry.has_image_layer = pdf_meta.get("has_image_layer")
        entry.page_count = pdf_meta.get("page_count")
        entry.is_encrypted = pdf_meta.get("is_encrypted")
    return entry


def apply_file_registry_to_provenance(
    provenance: Any,
    registry_entry: dict[str, Any] | None,
    *,
    file_path: str = "",
) -> None:
    """Merge FileRegistry entry into ParseResult.provenance (CCC-1)."""
    if registry_entry is None:
        return
    from docmirror.models.entities.parse_result import ProvenanceInfo

    if provenance is None:
        provenance = ProvenanceInfo()
    provenance.file_path = registry_entry.get("path") or file_path or provenance.file_path
    provenance.file_id = registry_entry.get("file_id") or provenance.file_id
    provenance.file_hash = (
        registry_entry.get("sha256_strict")
        or registry_entry.get("sha256_fast")
        or provenance.file_hash
    )
    if registry_entry.get("mime_type"):
        provenance.mime_type = registry_entry["mime_type"]
    if registry_entry.get("size"):
        provenance.file_size = int(registry_entry["size"])
    fp = FileFingerprint.from_registry_entry(registry_entry)
    provenance.document_properties["fingerprint"] = fp.model_dump(exclude_none=True)
