"""
TypedSpan — cross-subsystem type annotation for KV fields (GA 1.0 Step 7).

Projects type_gate's 7-type inference capability from FieldCell (table cell)
subsystem into KV field extraction. Every matched community field carries
optional TypedSpan annotations with primary type, type confidence, and all
candidate types.

Usage::
    from docmirror.models.mirror.typed_span import TypedSpan, SpanType
    span = TypedSpan.of("CNY 12,345.67")
    # span.primary_type = "amount", span.type_confidence = 0.95
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SpanType:
    """Single inferred type with confidence score."""

    type_name: str
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"type_name": self.type_name, "confidence": self.confidence}


@dataclass
class TypedSpan:
    """Type annotation for a single KV field value.

    Carries the primary (most confident) inferred type and all candidate
    types from type_gate.infer_types().
    """

    field_key: str = ""
    field_value: str = ""
    primary_type: str = "text"
    type_confidence: float = 0.0
    candidate_types: list[SpanType] = field(default_factory=list)
    is_empty: bool = False

    @classmethod
    def of(cls, field_key: str, field_value: str) -> TypedSpan:
        """Build TypedSpan by calling type_gate.infer_types on the value."""
        from docmirror.core.ocr.field_grid.type_gate import infer_types

        inferred = infer_types(field_value)
        if not field_value or not field_value.strip():
            return cls(field_key=field_key, field_value=field_value, primary_type="empty", is_empty=True)

        # Map inferred types: the first non-text type wins, text is fallback
        non_text = [t for t in inferred if t not in ("text", "empty")]
        primary = non_text[0] if non_text else (inferred[0] if inferred else "text")

        # Simple confidence heuristic: specific types > generic
        if primary in ("text",):
            conf = 0.3
        elif primary in ("amount", "currency"):
            conf = 0.85
        elif primary == "date":
            conf = 0.9
        elif primary == "long_id":
            conf = 0.8
        elif primary == "status_word":
            conf = 0.7
        elif primary == "page_footer":
            conf = 0.95
        elif primary == "status_date":
            conf = 0.9
        else:
            conf = 0.6

        candidates = [SpanType(type_name=t, confidence=(conf if t == primary else 0.3)) for t in inferred]

        return cls(
            field_key=field_key,
            field_value=field_value,
            primary_type=primary,
            type_confidence=round(conf, 2),
            candidate_types=candidates,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_key": self.field_key,
            "field_value": self.field_value,
            "primary_type": self.primary_type,
            "type_confidence": self.type_confidence,
            "candidate_types": [ct.to_dict() for ct in self.candidate_types],
            "is_empty": self.is_empty,
        }


def annotate_typed_spans(fields: dict[str, Any]) -> list[TypedSpan]:
    """Annotate all KV fields with TypedSpan type inference.

    Args:
        fields: Dict of field_key → field_value from community extract.

    Returns:
        List of TypedSpan annotations, one per non-empty field.
    """
    spans: list[TypedSpan] = []
    for key, value in fields.items():
        if isinstance(value, str) and value.strip():
            spans.append(TypedSpan.of(key, value))
        elif value is not None:
            spans.append(TypedSpan.of(key, str(value)))
    return spans


__all__ = ["TypedSpan", "SpanType", "annotate_typed_spans"]
