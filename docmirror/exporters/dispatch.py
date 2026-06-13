# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Unified ParseResult export dispatch (json/udif handled by API; tabular + chunks here)."""

from __future__ import annotations

from docmirror.models.entities.parse_result import ParseResult


def export_parse_result(result: ParseResult, fmt: str) -> tuple[bytes | str, str, str]:
    """Export ParseResult in a downloadable format.

    Returns:
        ``(payload, media_type, filename_suffix)``
    """
    normalized = fmt.lower().strip()
    if normalized == "chunks":
        from docmirror.exporters.rag_chunks import export_chunks_payload

        return export_chunks_payload(result)

    from docmirror.exporters.tabular import export_parse_result as export_tabular

    return export_tabular(result, normalized)


def save_parse_result_export(result: ParseResult, fmt: str, output_path) -> None:
    """Write export payload to *output_path* (CLI helper)."""
    payload, _, _suffix = export_parse_result(result, fmt)
    path = output_path
    if isinstance(payload, bytes):
        path.write_bytes(payload)
    else:
        path.write_text(payload, encoding="utf-8")
