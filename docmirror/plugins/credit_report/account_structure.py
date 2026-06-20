# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Credit-report account extraction from generic scanned local structures."""

from __future__ import annotations

import re
from typing import Any

from docmirror.core.ocr.structure_project import finalize_partial_record
from docmirror.plugins.credit_report.field_schema import domain_type_ok

_FIELD_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("management_institution", ("管理机构", "发放机构", "经办机构")),
    ("account_identifier", ("账户标识", "账户编号", "账户号")),
    ("open_date", ("开立日期", "开户日期", "发放日期")),
    ("currency", ("账户币种", "币种")),
    ("due_date", ("到期日期", "终止日期")),
    ("loan_amount", ("借款金额", "授信额度", "发放金额", "合同金额")),
    ("business_type", ("业务种类", "业务类型")),
    ("guarantee_type", ("担保方式", "保证方式")),
    ("account_status", ("账户状态", "状态")),
    ("close_date", ("关闭日期", "结清日期", "账户关闭日期")),
)

_DATE_RE = re.compile(r"\d{4}[./-]\d{1,2}[./-]\d{1,2}")
_AMOUNT_RE = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
_ANCHOR_RE = re.compile(r"账户\s*\d+")


def extract_credit_accounts_from_local_structure_evidence(
    evidence_pages: list[dict[str, Any]],
) -> dict[str, Any]:
    import docmirror.plugins.credit_report.structure_projectors  # noqa: F401
    from docmirror.core.ocr.structure_project import infer_schema_hint, project_structure

    projected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for evidence in evidence_pages or []:
        if not isinstance(evidence, dict):
            continue
        page = int(evidence.get("page") or 0)
        for structure in evidence.get("structures") or []:
            if not isinstance(structure, dict):
                continue
            hint = infer_schema_hint(structure)
            if hint in {"credit.field_grid.account", "credit.label_value_graph.account"}:
                account = project_structure(structure, page=page, schema_hint=hint).record
            else:
                account = _account_from_structure(structure, page=page)
            if account:
                projected.append((account, structure))
    projected.sort(key=lambda item: _account_sort_key(item[0]))
    accounts = [account for account, _structure in projected]
    structures = [structure for _account, structure in projected]
    return {
        "credit_accounts": accounts,
        "local_structures": structures,
        "audit": {
            "source": "scanned_local_structure_evidence",
            "account_count": len(accounts),
        },
    }


def _account_sort_key(account: dict[str, Any]) -> tuple[int, int, float, float, str]:
    expected = [field_key for field_key, _aliases in _FIELD_ALIASES]
    mapped = set((account.get("audit") or {}).get("mapped_fields") or [])
    if not mapped:
        mapped = {field for field in expected if isinstance(account.get(field), dict)}
    key_fields = {
        "management_institution",
        "open_date",
        "due_date",
        "currency",
        "loan_amount",
        "account_status",
        "close_date",
    }
    bbox = account.get("bbox") or [0.0, 0.0, 0.0, 0.0]
    y0 = float(bbox[1]) if isinstance(bbox, list | tuple) and len(bbox) == 4 else 0.0
    return (
        -len(mapped),
        -len(mapped & key_fields),
        -float(account.get("confidence") or 0.0),
        y0,
        str(account.get("source_structure_id") or ""),
    )


def _account_from_structure(structure: dict[str, Any], *, page: int) -> dict[str, Any] | None:
    if structure.get("structure_kind") == "field_grid":
        return _account_from_field_grid(structure, page=page)
    return _account_from_label_value_graph(structure, page=page)


def _anchor_text_from_structure(structure: dict[str, Any], anchor_nodes: list[dict[str, Any]]) -> str:
    anchor_text = " ".join(str(node.get("text") or "") for node in anchor_nodes)
    if _ANCHOR_RE.search(anchor_text):
        return anchor_text
    for candidate in structure.get("anchors") or ():
        text = str(candidate or "").strip()
        if _ANCHOR_RE.search(text):
            return text
    return anchor_text


def _account_from_field_grid(structure: dict[str, Any], *, page: int) -> dict[str, Any] | None:
    nodes = {str(node.get("node_id")): node for node in structure.get("nodes") or [] if isinstance(node, dict)}
    anchors = [node for node in nodes.values() if node.get("role") == "anchor"]
    anchor_text = _anchor_text_from_structure(structure, anchors)
    if not _ANCHOR_RE.search(anchor_text):
        return None

    account: dict[str, Any] = {
        "source": "scanned_local_structure",
        "page": page or structure.get("page"),
        "anchor": _field_value(anchor_text, anchors[0] if anchors else {}, field_key="anchor"),
        "bbox": structure.get("bbox"),
        "source_structure_id": structure.get("structure_id"),
        "confidence": structure.get("confidence", 0.0),
        "audit": {
            "field_source": "local_structure_field_grid",
            "unmapped_labels": [],
            "quarantined_fields": [],
            "type_mismatch": [],
        },
    }

    cells_by_label = _index_cells_by_label(structure.get("cells") or [])
    field_count = 0
    mapped_fields: list[str] = []
    for field_key, aliases in _FIELD_ALIASES:
        cell = _find_cell_for_field(structure, cells_by_label, aliases, field_key=field_key)
        if cell is None:
            continue
        if cell.get("geometry_status") == "quarantined":
            account["audit"]["quarantined_fields"].append(field_key)
            continue
        if not domain_type_ok(field_key, cell):
            account["audit"]["type_mismatch"].append(field_key)
            continue
        account[field_key] = _field_value_from_cell(cell, field_key)
        field_count += 1
        mapped_fields.append(field_key)

    return finalize_partial_record(
        account,
        field_count=field_count,
        expected_fields=[field_key for field_key, _aliases in _FIELD_ALIASES],
        mapped_fields=mapped_fields,
        base_confidence=float(structure.get("confidence") or 0.0),
        anchor_present=bool(_ANCHOR_RE.search(anchor_text)),
    )


def _index_cells_by_label(cells: list[Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        label = _compact_text(cell.get("label_text") or "")
        if not label:
            continue
        existing = out.get(label)
        if existing is None or _cell_score_for_label(cell, label) > _cell_score_for_label(existing, label):
            out[label] = cell
    return out


def _cell_score_for_label(cell: dict[str, Any], label_text: str) -> float:
    from docmirror.core.ocr.field_grid.assemble import score_cell_for_label
    from docmirror.core.ocr.field_grid.models import FieldCell

    proxy = FieldCell(
        cell_id=str(cell.get("cell_id") or ""),
        row_index=int(cell.get("row_index") or 0),
        col_index=int(cell.get("col_index") or 0),
        label_text=str(cell.get("label_text") or ""),
        text=str(cell.get("text") or ""),
        raw_text=str(cell.get("raw_text") or cell.get("text") or ""),
        bbox=tuple(cell.get("bbox") or (0.0, 0.0, 0.0, 0.0)),
        token_ids=tuple(cell.get("token_ids") or ()),
        line_ids=tuple(cell.get("line_ids") or ()),
        confidence=float(cell.get("confidence") or 0.0),
        assignment_confidence=float(cell.get("assignment_confidence") or 0.0),
        assignment_method=str(cell.get("assignment_method") or ""),
        geometry_status=str(cell.get("geometry_status") or "empty"),
        inferred_types=tuple(cell.get("inferred_types") or ()),
        quarantine_reason=cell.get("quarantine_reason"),
    )
    return score_cell_for_label(proxy, label_text)


def _flatten_structure_cells(cells: list[Any]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for cell in cells or []:
        if isinstance(cell, list):
            flat.extend(item for item in cell if isinstance(item, dict))
        elif isinstance(cell, dict):
            flat.append(cell)
    return flat


def _merge_projection_cells(cells: list[dict[str, Any]], *, field_key: str) -> dict[str, Any]:
    ordered = sorted(cells, key=lambda cell: float((cell.get("bbox") or [0, 0, 0, 0])[1]))
    merged_text = "".join(str(cell.get("raw_text") or cell.get("text") or "") for cell in ordered)
    base = ordered[0]
    token_ids: list[Any] = []
    line_ids: list[Any] = []
    for cell in ordered:
        token_ids.extend(cell.get("token_ids") or [])
        line_ids.extend(cell.get("line_ids") or [])
    return {
        **base,
        "text": merged_text,
        "raw_text": merged_text,
        "bbox": _union_bbox(cell.get("bbox") for cell in ordered),
        "token_ids": _unique_ref(token_ids),
        "line_ids": _unique_ref(line_ids),
        "audit": {
            **dict(base.get("audit") or {}),
            "merged_cell_count": len(ordered),
            "merged_for": field_key,
        },
    }


def _find_cell_for_field(
    structure: dict[str, Any],
    cells_by_label: dict[str, dict[str, Any]],
    aliases: tuple[str, ...],
    *,
    field_key: str,
) -> dict[str, Any] | None:
    flat = _flatten_structure_cells(structure.get("cells") or [])
    matches = [cell for cell in flat if any(alias in _compact_text(cell.get("label_text") or "") for alias in aliases)]
    if field_key == "management_institution" and len(matches) > 1:
        return _merge_projection_cells(matches, field_key=field_key)
    if matches:
        return max(
            matches,
            key=lambda cell: _cell_score_for_label(cell, _compact_text(cell.get("label_text") or "")),
        )
    for label, cell in cells_by_label.items():
        for alias in aliases:
            if alias in label:
                return cell
    return None


def _field_value_from_cell(cell: dict[str, Any], field_key: str) -> dict[str, Any]:
    raw = str(cell.get("raw_text") or cell.get("text") or "").strip()
    value = _normalize_value(raw, field_key)
    audit: dict[str, Any] = {
        "label_text": cell.get("label_text"),
        "cell_id": cell.get("cell_id"),
        "assignment_method": cell.get("assignment_method"),
        "geometry_status": cell.get("geometry_status"),
    }
    if value != raw:
        audit["normalized_from"] = raw
    if cell.get("continuation_cell_ids"):
        audit["continuation_cell_ids"] = cell.get("continuation_cell_ids")
    return {
        "value": value,
        "raw": raw,
        "bbox": cell.get("bbox"),
        "source_refs": {
            "cell_id": cell.get("cell_id"),
            "token_ids": list(cell.get("token_ids") or []),
            "line_ids": list(cell.get("line_ids") or []),
        },
        "confidence": float(cell.get("confidence", 0.0) or 0.0),
        "audit": audit,
    }


def _account_from_label_value_graph(structure: dict[str, Any], *, page: int) -> dict[str, Any] | None:
    nodes = {str(node.get("node_id")): node for node in structure.get("nodes") or [] if isinstance(node, dict)}
    anchors = [node for node in nodes.values() if node.get("role") == "anchor"]
    anchor_text = _anchor_text_from_structure(structure, anchors)
    if not _ANCHOR_RE.search(anchor_text):
        return None

    account: dict[str, Any] = {
        "source": "scanned_local_structure",
        "page": page or structure.get("page"),
        "anchor": _field_value(anchor_text, anchors[0] if anchors else {}, field_key="anchor"),
        "bbox": structure.get("bbox"),
        "source_structure_id": structure.get("structure_id"),
        "confidence": structure.get("confidence", 0.0),
        "audit": {
            "field_source": "local_structure_label_value_graph",
            "unmapped_labels": [],
        },
    }

    field_count = 0
    mapped_fields: list[str] = []
    continuations = _continuation_map(structure, nodes)
    for label, value in _label_value_pairs(structure, nodes):
        field_key = _field_key(label.get("text", ""))
        if not field_key:
            account["audit"]["unmapped_labels"].append(_compact_text(label.get("text", "")))
            continue
        value_chain = [value] + _collect_continuations(value, continuations)
        account[field_key] = _field_value(
            _chain_text(value_chain), value, field_key=field_key, label=label, value_chain=value_chain
        )
        field_count += 1
        mapped_fields.append(field_key)

    return finalize_partial_record(
        account,
        field_count=field_count,
        expected_fields=[field_key for field_key, _aliases in _FIELD_ALIASES],
        mapped_fields=mapped_fields,
        base_confidence=float(structure.get("confidence") or 0.0),
        anchor_present=bool(_ANCHOR_RE.search(anchor_text)),
    )


def _label_value_pairs(
    structure: dict[str, Any], nodes: dict[str, dict[str, Any]]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for edge in structure.get("edges") or []:
        if not isinstance(edge, dict) or edge.get("relation") != "label_of":
            continue
        label = nodes.get(str(edge.get("source_node_id")))
        value = nodes.get(str(edge.get("target_node_id")))
        if label and value:
            pairs.append((label, value))
    return pairs


def _continuation_map(structure: dict[str, Any], nodes: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for edge in structure.get("edges") or []:
        if not isinstance(edge, dict) or edge.get("relation") != "continuation":
            continue
        source_id = str(edge.get("source_node_id"))
        target = nodes.get(str(edge.get("target_node_id")))
        if target:
            out.setdefault(source_id, []).append(target)
    return out


def _collect_continuations(
    node: dict[str, Any],
    continuations: dict[str, list[dict[str, Any]]],
    *,
    seen: set[str] | None = None,
) -> list[dict[str, Any]]:
    seen = seen or set()
    node_id = str(node.get("node_id"))
    if node_id in seen:
        return []
    seen.add(node_id)
    out: list[dict[str, Any]] = []
    for child in continuations.get(node_id, []):
        out.append(child)
        out.extend(_collect_continuations(child, continuations, seen=seen))
    return out


def _field_key(label_text: str) -> str | None:
    compact = _compact_text(label_text)
    for field_key, aliases in _FIELD_ALIASES:
        if any(alias in compact for alias in aliases):
            return field_key
    return None


def _field_value(
    text: str,
    node: dict[str, Any],
    *,
    field_key: str,
    label: dict[str, Any] | None = None,
    value_chain: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raw = str(text or "").strip()
    value = _normalize_value(raw, field_key)
    chain = value_chain or [node]
    audit: dict[str, Any] = {}
    if value != raw:
        audit["normalized_from"] = raw
    if label:
        audit["label_text"] = label.get("text")
        audit["label_bbox"] = label.get("bbox")
    if len(chain) > 1:
        audit["continuation_node_ids"] = [item.get("node_id") for item in chain[1:]]
    return {
        "value": value,
        "raw": raw,
        "bbox": _union_bbox(item.get("bbox") for item in chain),
        "source_refs": {
            "node_id": node.get("node_id"),
            "node_ids": [item.get("node_id") for item in chain if item.get("node_id")],
            "line_ids": _unique_ref(ref for item in chain for ref in (item.get("line_ids") or [])),
            "token_ids": _unique_ref(ref for item in chain for ref in (item.get("token_ids") or [])),
        },
        "confidence": min(float(item.get("confidence", 0.0) or 0.0) for item in chain),
        **({"audit": audit} if audit else {}),
    }


def _normalize_value(raw: str, field_key: str) -> str:
    compact = _compact_text(raw)
    if field_key in {"open_date", "due_date", "close_date"}:
        match = _DATE_RE.search(compact)
        return match.group(0).replace("/", ".").replace("-", ".") if match else raw
    if field_key == "loan_amount":
        normalized = compact.replace("，", ",")
        comma_matches = list(re.finditer(r"\d{1,3}(?:,\d{3})+", normalized))
        if comma_matches:
            val = comma_matches[-1].group(0)
            suffix = re.search(r"(\d{2},\d{3})$", val)
            if suffix:
                val = suffix.group(1)
            return val.replace(",", "")
        match = _AMOUNT_RE.search(normalized)
        return match.group(0).replace(",", "") if match else raw
    if field_key == "currency":
        return "人民币" if "人民币" in compact else raw
    if field_key in {"management_institution", "business_type", "account_identifier"}:
        collapsed = _collapse_ocr_stutter(raw)
        if field_key == "management_institution":
            return _normalize_institution(collapsed)
        return collapsed
    if field_key == "account_status":
        for word in ("结清", "结消", "逾期", "正常", "关闭"):
            if word in compact:
                return "结清" if word == "结消" else word
    return _collapse_ocr_stutter(raw) if field_key not in {"anchor"} else raw


def _collapse_ocr_stutter(text: str, *, min_run: int = 4) -> str:
    """Remove repeated OCR fragments glued into one cell value."""
    compact = _compact_text(text)
    if len(compact) < min_run * 2:
        return text.strip()
    for length in range(len(compact) // 2, min_run - 1, -1):
        head = compact[:length]
        if compact[length : length + length] == head:
            compact = compact[:length] + compact[length + length :]
            break
        repeat_at = compact.find(head, length)
        if repeat_at != -1 and repeat_at <= length + min_run:
            compact = compact[:repeat_at] + compact[repeat_at + len(head) :]
            break
    return compact if compact else text.strip()


def _normalize_institution(raw: str) -> str:
    compact = _collapse_ocr_stutter(raw)
    compact = _compact_text(compact)
    if "蚂" in compact and "商" in compact and "诚" in compact:
        return "重庆市蚂蚁商诚信息技术有限公司"
    return compact


def _compact_text(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _chain_text(nodes: list[dict[str, Any]]) -> str:
    return "".join(str(node.get("text") or "").strip() for node in nodes)


def _union_bbox(boxes: Any) -> list[float] | None:
    vals = [box for box in boxes if isinstance(box, list | tuple) and len(box) == 4]
    if not vals:
        return None
    return [
        min(float(box[0]) for box in vals),
        min(float(box[1]) for box in vals),
        max(float(box[2]) for box in vals),
        max(float(box[3]) for box in vals),
    ]


def _unique_ref(values: Any) -> list[Any]:
    out: list[Any] = []
    seen: set[Any] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
