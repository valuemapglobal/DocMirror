"""
LLM Document Restorer Middleware
================================

When the traditional extraction pipeline fails to detect tables or produces
too few entities, this middleware calls a cloud LLM API to reconstruct table
structure and key-value fields from the raw OCR text.

⚠️  Cloud API only. Local LLM inference (Ollama, GGUF) is NOT supported
    for production use due to inference speed constraints on CPU hardware.

Trigger condition:
    table_count == 0 AND (entity_count < 3 OR total_text > 200 chars)

The LLM receives the raw ``ParseResult.full_text`` (which may include QGE
fallback text) and returns a JSON object containing ``tables`` and ``fields``.
These are injected into ``ParseResult.pages[0].tables`` (as ``TableBlock``)
and ``ParseResult.pages[0].key_values`` (as ``KeyValuePair``).

Configuration via environment variables:
    DOCMIRROR_LLM_ENABLED=true           (default: false)
    DOCMIRROR_LLM_API_KEY=sk-xxx         (required when enabled)
    DOCMIRROR_LLM_API_BASE=https://...   (default: OpenAI)
    DOCMIRROR_LLM_MODEL=gpt-4o-mini      (default: gpt-4o-mini)
    DOCMIRROR_LLM_TIMEOUT=60             (seconds, default: 60)
"""

from __future__ import annotations

import json
import logging
import os

from docmirror.models.entities.parse_result import (
    CellValue,
    KeyValuePair,
    ParseResult,
    TableBlock,
    TableRow,
)

from ..base import BaseMiddleware

logger = logging.getLogger(__name__)

# ── System prompt ──

SYSTEM_PROMPT = """You are an engine that extracts structured information from OCR noise text. Your input comes from OCR recognition of scanned/photographed documents. The text may contain:
  - Recognition errors (visually similar characters, extra/missing characters)
  - Formatting chaos (missing spaces, field adhesion, line order disorder)
  - Mix of Chinese, English, and numbers

Your task: Discover structure within the noise and output clean, consistent JSON.

──── Output Format ────

You must return a JSON object with the following structure:

{
  "document_type": "Document type inferred from text content",
  "confidence": 0.0~1.0,
  "tables": [
    [
      ["header_1", "header_2", ...],
      ["cell_value_1", "cell_value_2", ...],
      ...
    ]
  ],
  "fields": {
    "field_name_1": "field_value_1",
    "field_name_2": "field_value_2",
    ...
  }
}

──── Extraction Rules ────

1. **tables**: Any tabular data — transaction records, invoice details, credit report lists, shareholder info, etc.
   Ensure each row has the same number of columns. Name headers appropriately.
   If amounts have positive/negative signs, preserve them. Amounts should not contain commas.

2. **fields**: All non-table key fields — name, account number, date, amount summary, address, etc.
   Name fields appropriately. Do not fabricate non-existent fields.

3. **correction**: Correct obvious OCR errors before extraction.

4. **missing**: If no table data exists in the text, use [] for tables.
   If no field data exists, use {} for fields. Do not fabricate non-existent values.

5. **JSON only**: Output only JSON, no explanations, comments, or markdown code block markers."""

USER_MESSAGE_TEMPLATE = "Extract structured information from the following OCR text:\n\n{text}"


# ── LLM call ──


def _call_llm(full_text: str) -> dict | None:
    """Call the LLM and return parsed JSON, or None on failure."""
    api_key = os.environ.get("DOCMIRROR_LLM_API_KEY")
    if not api_key:
        logger.info("[LlmRestorer] DOCMIRROR_LLM_API_KEY not set, skipped")
        return None

    try:
        import requests
    except ImportError:
        logger.warning('[LlmRestorer] requests is unavailable; install the AI extra with pip install "docmirror[ai]"')
        return None

    api_base = os.environ.get("DOCMIRROR_LLM_API_BASE") or "https://api.openai.com/v1"
    model = os.environ.get("DOCMIRROR_LLM_MODEL") or "gpt-4o-mini"
    timeout = int(os.environ.get("DOCMIRROR_LLM_TIMEOUT") or "60")

    max_chars = int(os.environ.get("DOCMIRROR_LLM_MAX_CHARS") or "8000")
    truncated = full_text[:max_chars]
    if len(full_text) > max_chars:
        truncated += f"\n... (truncated {len(full_text) - max_chars} chars)"

    url = f"{api_base.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "temperature": 0.0,
        "max_tokens": 4096,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_MESSAGE_TEMPLATE.format(text=truncated)},
        ],
    }

    response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    if response.status_code != 200:
        logger.warning(f"[LlmRestorer] LLM API returned {response.status_code}: {response.text[:200]}")
        return None

    content = response.json()["choices"][0]["message"]["content"]
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning(f"[LlmRestorer] Failed to parse LLM JSON: {e}")
        return None


# ── Injection helpers ──


def _inject_tables(result: ParseResult, tables: list) -> int:
    """Inject LLM-extracted tables into ParseResult as TableBlock objects."""
    count = 0
    for i, table in enumerate(tables):
        if not table or not isinstance(table, list):
            continue
        if len(table) < 2:
            continue

        headers = [str(h) for h in table[0]]
        rows = []
        for row_data in table[1:]:
            cells = [CellValue(text=str(c)) for c in row_data]
            rows.append(TableRow(cells=cells))

        table_block = TableBlock(
            table_id=f"llm_table_{i}",
            headers=headers,
            rows=rows,
            page=1,
            confidence=0.85,
            extraction_layer="llm_restorer",
            metadata={"source": "llm_restorer"},
        )

        if not result.pages:
            continue
        result.pages[0].tables.append(table_block)
        count += 1

    return count


def _inject_fields(result: ParseResult, fields: dict) -> int:
    """Inject LLM-extracted fields into ParseResult as KeyValuePair objects."""
    count = 0
    for key, value in fields.items():
        if not key or not value:
            continue
        kv = KeyValuePair(key=str(key), value=str(value), confidence=0.85)
        if not result.pages:
            continue
        result.pages[0].key_values.append(kv)
        count += 1

    return count


# ── Middleware ──


class LlmDocumentRestorer(BaseMiddleware):
    """Restore tables and entities from OCR text using an LLM."""

    DEPENDS_ON = ["EvidenceEngine"]
    PROVIDES = ["tables", "key_values"]

    def should_skip(self, result: ParseResult) -> bool:
        """Skip if LLM disabled or traditional pipeline already has enough."""
        if os.environ.get("DOCMIRROR_LLM_ENABLED") != "true":
            return True

        table_count = sum(len(p.tables) for p in result.pages) if result.pages else 0
        if table_count > 0:
            return True

        entity_count = sum(len(p.key_values) for p in result.pages) if result.pages else 0
        full_text = result.full_text or ""
        if entity_count >= 3 and len(full_text) < 500:
            return True

        if len(full_text) < 50:
            return True

        return False

    def process(self, result: ParseResult) -> ParseResult:
        """Call LLM, parse response, inject tables and fields into ParseResult."""
        if self.should_skip(result):
            return result

        full_text = result.full_text or ""
        logger.info(f"[LlmRestorer] Calling LLM with {len(full_text)} chars")

        try:
            data = _call_llm(full_text)
        except Exception as exc:
            logger.warning(f"[LlmRestorer] LLM call failed: {exc}")
            result.add_error(f"llm_restorer_call_failed: {exc}")
            return result

        if data is None:
            return result

        if not isinstance(data, dict):
            logger.warning(f"[LlmRestorer] LLM returned non-dict: {type(data).__name__}")
            return result

        tables = data.get("tables", [])
        if isinstance(tables, list) and tables:
            tc = _inject_tables(result, tables)
            if tc > 0:
                result.record_mutation(
                    "LlmDocumentRestorer",
                    target_block_id="pages",
                    field_changed="tables",
                    old_value=[],
                    new_value=f"{tc} tables (conf={data.get('confidence', '?')})",
                    reason="llm_restorer",
                )
                logger.info(f"[LlmRestorer] Injected {tc} tables")

        fields = data.get("fields", {})
        if isinstance(fields, dict) and fields:
            fc = _inject_fields(result, fields)
            if fc > 0:
                result.record_mutation(
                    "LlmDocumentRestorer",
                    target_block_id="pages",
                    field_changed="key_values",
                    old_value=[],
                    new_value=f"{fc} fields",
                    reason="llm_restorer",
                )
                logger.info(f"[LlmRestorer] Injected {fc} key-value fields")

        return result
