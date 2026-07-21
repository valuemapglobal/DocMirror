"""Dispatch table for lightweight output exporters."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from docmirror.output.dmir import serialize_dmir_json
from docmirror.output.markdown_renderer import render_markdown, render_markdown_from_vnext
from docmirror.runtime.serialization import dumps_json, to_json_safe

Exporter = Callable[[Any], tuple[str, str, str]]


class ExporterRegistry:
    def __init__(self) -> None:
        self._exporters: dict[str, Exporter] = {}

    def register(self, name: str, exporter: Exporter) -> None:
        self._exporters[name] = exporter

    def formats(self) -> list[str]:
        return sorted(self._exporters)

    def export(self, result: Any, format_name: str) -> tuple[str, str, str]:
        try:
            exporter = self._exporters[format_name]
        except KeyError as exc:
            supported = ", ".join(self.formats())
            raise ValueError(f"Unsupported export format {format_name!r}; supported: {supported}") from exc
        return exporter(result)


def export_dmir(result: Any) -> tuple[str, str, str]:
    return serialize_dmir_json(result), "application/json", ".dmir.json"


def export_json(result: Any) -> tuple[str, str, str]:
    return dumps_json(to_json_safe(result), indent=2), "application/json", ".json"


def export_parse_result(result: Any, format_name: str = "json", **kwargs: Any) -> tuple[str, str, str]:
    mirror_vnext = kwargs.get("mirror_vnext")
    if format_name == "markdown":
        if mirror_vnext:
            return render_markdown_from_vnext(mirror_vnext), "text/markdown", ".md"
        return render_markdown(result), "text/markdown", ".md"
    if format_name == "chunks":
        if mirror_vnext:
            from docmirror.output.mirror_vnext_projection import export_chunks_from_vnext

            chunks = export_chunks_from_vnext(mirror_vnext)
            return (
                dumps_json({"source": "mirror_vnext_reading_flow", "chunk_count": len(chunks), "chunks": chunks}),
                "application/json",
                ".chunks.json",
            )
        return (
            dumps_json({"source": "parse_result", "chunk_count": 0, "chunks": []}),
            "application/json",
            ".chunks.json",
        )
    if format_name in {"csv", "parquet"}:
        from docmirror.output.exporters.tabular import export_parse_result as export_tabular

        return export_tabular(result, format_name)
    return EXPORTER_REGISTRY.export(result, format_name)


EXPORTER_REGISTRY = ExporterRegistry()
EXPORTER_REGISTRY.register("dmir", export_dmir)
EXPORTER_REGISTRY.register("json", export_json)
EXPORTER_REGISTRY.register("markdown", lambda result: export_parse_result(result, "markdown"))
EXPORTER_REGISTRY.register("chunks", lambda result: export_parse_result(result, "chunks"))
EXPORTER_REGISTRY.register("csv", lambda result: export_parse_result(result, "csv"))
EXPORTER_REGISTRY.register("parquet", lambda result: export_parse_result(result, "parquet"))
EXPORTER_REGISTRY.register("html", lambda result: ("", "text/html", ".html"))
