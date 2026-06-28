"""Note reference extraction for financial statement rows."""

from __future__ import annotations

import re
from typing import Any

_CHINESE_NOTE_NUMERAL = r"一二三四五六七八九十百千万"


def extract_note_ref(row_cells: list[dict[str, Any]], label: str) -> str | None:
    candidates = [str(cell.get("text") or "").strip() for cell in row_cells]
    candidates.append(label)
    allow_bare_ref = any("附注" in candidate for candidate in candidates)
    for text in candidates:
        note_ref = normalize_note_ref(text, allow_bare=allow_bare_ref)
        if note_ref:
            return note_ref
    return None


def normalize_note_ref(text: str, *, allow_bare: bool = False) -> str | None:
    cleaned = str(text or "").replace(" ", "").replace("\u3000", "")
    if not cleaned:
        return None
    match = re.search(rf"附注[（(]?([{_CHINESE_NOTE_NUMERAL}0-9]{{1,6}})[）)]?", cleaned)
    if match:
        return f"附注{match.group(1)}"
    if not allow_bare:
        return None
    if re.fullmatch(rf"[{_CHINESE_NOTE_NUMERAL}]{{1,6}}", cleaned):
        return f"附注{cleaned}"
    if re.fullmatch(r"[0-9]{1,3}", cleaned):
        return f"附注{cleaned}"
    return None
