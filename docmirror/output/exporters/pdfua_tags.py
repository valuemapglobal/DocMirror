"""PDF/UA tag mapping and structure helpers."""

from __future__ import annotations

from typing import Any


def dmir_to_pdf_tag(element_type: str, element: dict[str, Any]) -> str:
    if element_type == "text":
        level = str(element.get("level", "body")).lower()
        if level == "title":
            return "H1"
        if level.startswith("h") and level[1:].isdigit() and 1 <= int(level[1:]) <= 6:
            return level.upper()
        if level == "watermark":
            return "Artifact"
        return "P"
    if element_type == "table":
        return "Table"
    if element_type == "kv":
        return "P"
    if element_type == "image":
        return "Figure"
    raise ValueError(f"Unknown DMIR element type: {element_type}")


def get_table_structure_tags(headers: list[str], data_rows: list[dict[str, Any]]) -> list[tuple[str, list[str]]]:
    col_count = max(len(headers), 1)
    rows = [("TR", ["TH"] * col_count)]
    for row in data_rows:
        cells = row.get("cells") or []
        rows.append(("TR", ["TD"] * max(len(cells), col_count)))
    return rows


def build_pdfua_struct_tree(dmir: dict[str, Any], page_refs: list[Any]) -> list[dict[str, Any]]:
    from pypdf.generic import DictionaryObject, NameObject

    elements: list[dict[str, Any]] = [
        {"_dict": DictionaryObject({NameObject("/S"): NameObject("/Document")}), "_parent_idx": None, "_child_indices": []}
    ]
    pages = dmir.get("document", {}).get("pages", [])
    for page_index, page in enumerate(pages):
        sect_idx = len(elements)
        elements[0]["_child_indices"].append(sect_idx)
        elements.append(
            {"_dict": DictionaryObject({NameObject("/S"): NameObject("/Sect")}), "_parent_idx": 0, "_child_indices": []}
        )
        content_items = list(page.get("texts", []) or []) + list(page.get("tables", []) or []) + list(page.get("key_values", []) or [])
        for item_index, item in enumerate(content_items):
            kind = "table" if "headers" in item or "data_rows" in item else "kv" if "key" in item else "text"
            tag = dmir_to_pdf_tag(kind, item)
            child_idx = len(elements)
            elements[sect_idx]["_child_indices"].append(child_idx)
            elements.append(
                {
                    "_dict": DictionaryObject(
                        {
                            NameObject("/S"): NameObject(f"/{tag}"),
                            NameObject("/Type"): NameObject("/MCR"),
                        }
                    ),
                    "_parent_idx": sect_idx,
                    "_child_indices": [],
                    "_page_index": page_index,
                    "_mcid": item_index,
                    "_page_ref": page_refs[page_index] if page_index < len(page_refs) else None,
                }
            )
    return elements
