"""Schema-driven projection helpers for DMIR payloads."""

from __future__ import annotations

from typing import Any


def _resolve_jsonpath(data: Any, path: str) -> Any:
    """Resolve a small JSONPath subset used by built-in projection templates."""
    if not path.startswith("$."):
        return None
    parts = path[2:].split(".")
    current: Any = data
    for part in parts:
        wildcard = part.endswith("[*]")
        key = part[:-3] if wildcard else part
        if isinstance(current, list):
            values = []
            for item in current:
                if isinstance(item, dict) and key in item:
                    value = item[key]
                    if isinstance(value, list):
                        values.extend(value)
                    else:
                        values.append(value)
            current = values
        elif isinstance(current, dict) and key in current:
            current = current[key]
            if wildcard and not isinstance(current, list):
                current = []
        else:
            return None
    return current


def _transform_table_to_markdown(tables: Any) -> str:
    if not tables:
        return ""
    rendered: list[str] = []
    for table in tables:
        headers = table.get("headers") or []
        rows = table.get("data_rows") or []
        if not headers and not rows:
            continue
        rendered.append("| " + " | ".join(str(h) for h in headers) + " |")
        rendered.append("| " + " | ".join("---" for _ in headers) + " |")
        for row in rows:
            cells = row.get("cells") or []
            rendered.append("| " + " | ".join(str(cell.get("text", "")) for cell in cells) + " |")
    return "\n".join(rendered)


class ProjectionEngine:
    """Project DMIR into lightweight framework-specific payloads or code."""

    _templates = {"langchain", "llamaindex", "haystack", "spring-ai", "semantic-kernel"}

    def templates_available(self) -> list[str]:
        return sorted(self._templates)

    def project_to_dict(self, dmir: dict[str, Any], template: str) -> dict[str, Any]:
        if template not in self._templates:
            raise ValueError(f"Unknown projection template: {template}")
        document = dmir.get("document", {})
        meta = {
            "document_type": document.get("type"),
            "confidence": dmir.get("quality", {}).get("confidence"),
            **(document.get("properties") or {}),
        }
        tables_markdown = _transform_table_to_markdown(
            document.get("pages", [{}])[0].get("tables", []) if document.get("pages") else document.get("tables")
        )
        if tables_markdown:
            meta["tables_markdown"] = tables_markdown
        content = document.get("full_text", "")
        if template == "llamaindex":
            return {"text": content, "extra_info": meta}
        if template == "haystack":
            return {"content": content, "meta": meta}
        return {"page_content": content, "metadata": meta}

    def project(self, dmir: dict[str, Any], template: str) -> str:
        payload = self.project_to_dict(dmir, template)
        if template == "langchain":
            return f"Document(page_content={payload['page_content']!r}, metadata={payload['metadata']!r})"
        return repr(payload)

    def project_imports(self, template: str) -> list[str]:
        if template == "langchain":
            return ["from langchain_core.documents import Document"]
        return []
