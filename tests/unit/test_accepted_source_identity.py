# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from docmirror.configs.format.resolver import resolve_capability
from docmirror.framework.dispatcher import ParserDispatcher
from docmirror.input.acceptance import accept_source
from docmirror.input.models import AcceptedSource, InputAcceptanceReport


def test_accept_source_binds_private_snapshot_and_preserves_original_identity(tmp_path: Path):
    original = tmp_path / "source.xml"
    accepted_bytes = ("<root>" + "content" * 30 + "</root>").encode()
    original.write_bytes(accepted_bytes)

    accepted = accept_source(original)
    try:
        assert accepted.path != original
        assert accepted.display_path == original
        assert accepted.path.read_bytes() == accepted_bytes
        assert accepted.verify_content_identity()

        original.write_bytes(b"changed after acceptance" * 20)
        assert accepted.path.read_bytes() == accepted_bytes
        assert accepted.verify_content_identity()
    finally:
        snapshot = accepted.path
        accepted.cleanup()
    assert not snapshot.exists()


def test_dispatcher_rejects_tampered_accepted_content_before_adapter(tmp_path: Path):
    path = tmp_path / "source.xml"
    payload = ("<root>" + "content" * 30 + "</root>").encode()
    path.write_bytes(payload)
    accepted = AcceptedSource(
        path=path,
        original_name=path.name,
        size_bytes=len(payload),
        detected_mime="application/xml",
        sha256=hashlib.sha256(payload).hexdigest(),
        capability=resolve_capability(path, "application/xml"),
        acceptance=InputAcceptanceReport(),
    )
    path.write_bytes(payload + b"tampered")

    result = asyncio.run(ParserDispatcher().process(accepted))

    assert result.status.value == "failure"
    assert result.error is not None
    assert result.error.code == "INPUT_IDENTITY_MISMATCH"
