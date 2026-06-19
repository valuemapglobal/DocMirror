# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Unified ParseResult export dispatch (json/udif handled by API; tabular + chunks here)."""

from __future__ import annotations

import html

from dataclasses import dataclass
from collections.abc import Callable

from docmirror.models.entities.parse_result import ParseResult

ExportFn = Callable[[ParseResult], tuple[bytes | str, str, str]]


def export_to_html(result: ParseResult) -> str:
    """Export ParseResult text to a minimal standalone HTML document."""
    title = getattr(getattr(result, "entities", None), "document_type", "") or "DocMirror Export"
    body = html.escape(getattr(result, "full_text", "") or "")
    title_escaped = html.escape(str(title))
    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        f"  <title>{title_escaped}</title>\n"
        "  <style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "line-height:1.5;margin:32px;max-width:960px}pre{white-space:pre-wrap;"
        "word-break:break-word}</style>\n"
        "</head>\n"
        f"<body><h1>{title_escaped}</h1><pre>{body}</pre></body>\n"
        "</html>\n"
    )


@dataclass(frozen=True)
class ExporterSpec:
    name: str
    export: ExportFn


class ExporterRegistry:
    """Registry for ParseResult export formats."""

    def __init__(self) -> None:
        self._registry: dict[str, ExporterSpec] = {}

    def register(self, name: str, export: ExportFn) -> None:
        normalized = name.lower().strip()
        self._registry[normalized] = ExporterSpec(normalized, export)

    def export(self, result: ParseResult, fmt: str) -> tuple[bytes | str, str, str]:
        normalized = fmt.lower().strip()
        spec = self._registry.get(normalized)
        if spec is None:
            raise ValueError(f"unsupported export format: {fmt}")
        return spec.export(result)

    def formats(self) -> tuple[str, ...]:
        return tuple(sorted(self._registry))


def _export_chunks(result: ParseResult) -> tuple[str, str, str]:
    from docmirror.exporters.rag_chunks import export_chunks_payload

    editions = getattr(result, "editions", None)
    mirror = getattr(result, "mirror", result)
    return export_chunks_payload(mirror, editions=editions)


def _export_html(result: ParseResult) -> tuple[str, str, str]:
    return export_to_html(result), "text/html", ".html"


def _export_tabular(fmt: str) -> ExportFn:
    def _inner(result: ParseResult) -> tuple[bytes | str, str, str]:
        from docmirror.exporters.tabular import export_parse_result as export_tabular

        return export_tabular(result, fmt)

    return _inner


EXPORTER_REGISTRY = ExporterRegistry()
EXPORTER_REGISTRY.register("chunks", _export_chunks)
EXPORTER_REGISTRY.register("html", _export_html)
EXPORTER_REGISTRY.register("csv", _export_tabular("csv"))
EXPORTER_REGISTRY.register("parquet", _export_tabular("parquet"))


def export_parse_result(
    result: ParseResult,
    fmt: str,
    *,
    editions: dict | None = None,
) -> tuple[bytes | str, str, str]:
    """Export ParseResult in a downloadable format.

    When *result* is a ``PerceiveResult`` envelope, Core ``mirror`` is exported.
    Pass *editions* (or use ``result.editions``) so chunk export can read plugin
    ``data.sections`` (Architecture A).

    Returns:
        ``(payload, media_type, filename_suffix)``
    """
    mirror = getattr(result, "mirror", result)
    merged_editions = editions if editions is not None else getattr(result, "editions", None)
    normalized = fmt.lower().strip()
    if normalized == "chunks":
        from docmirror.exporters.rag_chunks import export_chunks_payload

        return export_chunks_payload(mirror, editions=merged_editions)
    return EXPORTER_REGISTRY.export(mirror, fmt)


def save_parse_result_export(result: ParseResult, fmt: str, output_path) -> None:
    """Write export payload to *output_path* (CLI helper)."""
    payload, _, _suffix = export_parse_result(result, fmt)
    path = output_path
    if isinstance(payload, bytes):
        path.write_bytes(payload)
    else:
        path.write_text(payload, encoding="utf-8")
