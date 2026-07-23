# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Atomic artifact persistence with no access to ParseResult."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from docmirror.runtime.serialization import dumps_json


class ArtifactWriter:
    """Write pre-rendered artifacts beneath one task directory atomically."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def write_text(self, name: str, content: str, *, encoding: str = "utf-8") -> Path:
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding=encoding) as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            try:
                directory_fd = os.open(target.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                # Some filesystems/platforms do not support directory fsync.
                pass
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def write_json(self, name: str, payload: object) -> Path:
        return self.write_text(name, dumps_json(payload, ensure_ascii=False, indent=2))


__all__ = ["ArtifactWriter"]
