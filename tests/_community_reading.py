# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared assertions for the Community reading-view contract."""

from __future__ import annotations

from typing import Any


def _resolve_data_path(data: dict[str, Any], path: str) -> Any:
    current: Any = {"data": data}
    for token in path.lstrip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def assert_community_reading_view(data: dict[str, Any]) -> None:
    """Assert reference integrity without requiring non-empty document content."""
    assert isinstance(data.get("sections"), list)
    assert isinstance(data.get("tables"), list)
    assert isinstance(data.get("notes"), list)
    assert isinstance(data.get("document_flow"), list)
    sections = {item["id"] for item in data["sections"]}
    tables = {item["id"] for item in data["tables"]}
    notes = {item["id"] for item in data["notes"]}
    record_ids = {str(item["id"]) for item in data.get("records") or [] if isinstance(item, dict) and item.get("id")}
    assert [item["order"] for item in data["document_flow"]] == list(range(1, len(data["document_flow"]) + 1))
    for item in data["document_flow"]:
        if item["kind"] == "section":
            assert item["ref_id"] in sections
        elif item["kind"] == "table":
            assert item["ref_id"] in tables
        elif item["kind"] == "note":
            assert item["ref_id"] in notes
        elif item["kind"] == "field_group":
            assert all(key in (data.get("fields") or {}) for key in item["field_keys"])
    for table in data["tables"]:
        assert not ({"rows", "records", "line_items"} & set(table))
        data_ref = table.get("data_ref")
        if isinstance(data_ref, dict):
            assert _resolve_data_path(data, data_ref["path"]) is not None
        elif isinstance(data_ref, str):
            assert _resolve_data_path(data, data_ref) is not None
        if table.get("record_ids"):
            assert set(table["record_ids"]) <= record_ids
    for note in data["notes"]:
        if note.get("content_ref"):
            assert _resolve_data_path(data, note["content_ref"]) not in (None, "")
    assert not ({"notes", "document_flow"} & {item["id"] for item in data.get("datasets") or []})


__all__ = ["assert_community_reading_view"]
