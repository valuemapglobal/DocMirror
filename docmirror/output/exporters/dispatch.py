"""Dispatch table for lightweight output exporters."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from docmirror.output.dmir import serialize_dmir_json
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


def export_parse_result(result: Any, format_name: str = "json") -> tuple[str, str, str]:
    return EXPORTER_REGISTRY.export(result, format_name)


EXPORTER_REGISTRY = ExporterRegistry()
EXPORTER_REGISTRY.register("dmir", export_dmir)
EXPORTER_REGISTRY.register("json", export_json)
