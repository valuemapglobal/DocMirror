"""DMIR serializer for LLM/framework-friendly document output."""

from __future__ import annotations

from typing import Any

from docmirror.runtime.serialization import dumps_json, to_json_safe

DMIR_VERSION = "1.0"


def _value(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default)


def serialize_dmir(result: Any) -> dict[str, Any]:
    """Serialize a parse result into the DMIR dictionary format."""
    entities = _value(result, "entities")
    trust = _value(result, "trust")
    parser_info = _value(result, "parser_info")
    pages = to_json_safe(_value(result, "pages", []) or [])
    logical_tables = to_json_safe(_value(result, "logical_tables", []) or [])
    sections = to_json_safe(_value(result, "sections", []) or [])

    payload = {
        "dmir_version": DMIR_VERSION,
        "document": {
            "type": _value(entities, "document_type", "unknown") if entities is not None else "unknown",
            "properties": {
                "organization": _value(entities, "organization", ""),
                "subject_name": _value(entities, "subject_name", ""),
                "subject_id": _value(entities, "subject_id", ""),
                "document_date": _value(entities, "document_date", ""),
                "period_start": _value(entities, "period_start", ""),
                "period_end": _value(entities, "period_end", ""),
            },
            "pages": pages,
            "tables": logical_tables,
            "sections": sections,
            "full_text": _value(result, "full_text", "") or _value(result, "extractor_full_text", "") or "",
        },
        "quality": {
            "confidence": float(_value(result, "confidence", 0.0) or 0.0),
            "trust_score": float(_value(trust, "trust_score", 0.0) or 0.0),
            "validation_passed": bool(_value(trust, "validation_passed", False)),
            "is_forged": bool(_value(trust, "is_forged", False)),
            "forgery_reasons": to_json_safe(_value(trust, "forgery_reasons", []) or []),
        },
        "evidence": {
            "ledger": [],
            "summary": {},
        },
        "meta": {
            "parser": _value(parser_info, "parser_name", "DocMirror"),
            "version": _value(parser_info, "parser_version", "1.0"),
            "elapsed_ms": _value(parser_info, "elapsed_ms", 0),
            "page_count": _value(parser_info, "page_count", len(pages)),
            "table_count": _value(
                result, "total_tables", len(logical_tables) if isinstance(logical_tables, list) else 0
            ),
            "row_count": _value(result, "total_rows", 0),
            "extraction_method": _value(
                _value(parser_info, "extraction_method", ""), "value", _value(parser_info, "extraction_method", "")
            ),
            "ocr_engine": _value(parser_info, "ocr_engine", ""),
            "table_engine": _value(parser_info, "table_engine", ""),
            "overall_confidence": _value(parser_info, "overall_confidence", _value(result, "confidence", 0.0)),
            "warnings": to_json_safe(_value(parser_info, "warnings", []) or []),
            "dmir_version": DMIR_VERSION,
        },
    }
    safety_report = getattr(result, "_safety_report", None)
    if safety_report is not None:
        to_dict = getattr(safety_report, "to_dict", None)
        payload["safety"] = to_json_safe(to_dict() if callable(to_dict) else safety_report)
    return payload


def serialize_dmir_json(result: Any, **kwargs: Any) -> str:
    """Serialize a parse result into a DMIR JSON string."""
    kwargs.setdefault("indent", 2)
    return dumps_json(serialize_dmir(result), **kwargs)
