# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Prompt Injection Detector — Heuristic pattern matching for injection vectors.

Detects common prompt-injection patterns in extracted document text:
- "Ignore previous instructions" / "Ignore all above commands"
- "Forget everything you know"
- "You are now / You must act as"
- "Output the password/key/token/secret/flag"
- "System prompt / System message / System instruction"
- Chat-template markers (``<|im_start|>``, ``<|im_end|>``,
  ``[INST]``, ``[SYS]``, ``[SYSTEM]``)
- Markdown-based prompt separators (``### system``, ``### user``)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
import math
from collections import Counter


# ── Entropy-based detection ─────────────────────────────────────────────

# High-entropy threshold: strings with Shannon entropy above this
# are flagged as potentially encoded or obfuscated payloads.
# Base64 encoded text typically has entropy >= 4.5 bits/byte.
HIGH_ENTROPY_THRESHOLD = 4.5
MAX_ENTROPY_CHUNK_SIZE = 256  # maximum chunk size for entropy analysis


def shannon_entropy(data: str) -> float:
    """Compute Shannon entropy (bits per byte) of a string.

    A high entropy value suggests encoded or obfuscated content.
    Typical English text entropy is ~3.5–4.0 bits/char.
    Base64 encoded text is ~4.5–5.0 bits/char.
    Random bytes are close to 8.0 bits/byte.
    """
    if not data:
        return 0.0
    freq = Counter(data)
    length = len(data)
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


def scan_high_entropy(text: str) -> list[dict]:
    """Scan *text* for high-entropy segments.

    Slides a window over the text and identifies regions where
    Shannon entropy exceeds *HIGH_ENTROPY_THRESHOLD*.

    Returns a list of dicts with ``start``, ``end``, ``entropy``, and
    ``snippet`` keys for each high-entropy segment.
    """
    results = []
    if not text or len(text) < 8:
        return results

    # Check the whole text
    overall = shannon_entropy(text[:MAX_ENTROPY_CHUNK_SIZE])
    if overall >= HIGH_ENTROPY_THRESHOLD:
        results.append({
            "start": 0,
            "end": min(len(text), MAX_ENTROPY_CHUNK_SIZE),
            "entropy": round(overall, 2),
            "snippet": text[:min(80, len(text))],
        })
        return results  # Whole text is high-entropy, no need for sliding window

    # Sliding-window check every 64 chars
    step = 64
    window = 128
    for start in range(0, len(text) - window + 1, step):
        chunk = text[start:start + window]
        ent = shannon_entropy(chunk)
        if ent >= HIGH_ENTROPY_THRESHOLD:
            results.append({
                "start": start,
                "end": start + window,
                "entropy": round(ent, 2),
                "snippet": chunk[:80],
            })
    return results


# ── PDF metadata injection scanner ──────────────────────────────────────────

# PDF-specific injection markers that should never appear in metadata values
PDF_INJECTION_MARKERS: list[str] = [
    "%%EOF",
    "endobj",
    "endstream",
    "stream",
    "/Type",
    "/Page",
    "/Root",
    "/Info",
    "/Metadata",
    "obj<",
    ">>",
]


def scan_pdf_metadata_injection(metadata: dict[str, str]) -> list[str]:
    """Scan PDF metadata fields for injection payloads.

    Checks each metadata value for PDF object markers that would
    indicate a metadata injection attack (e.g. embedding %%EOF or
    endobj inside /Title or /Author to break the PDF structure).

    Args:
        metadata: Dict of PDF metadata fields (e.g. ``{"/Title": "...", "/Author": "..."}").

    Returns:
        List of field names that contain injection markers.
    """
    injected_fields: list[str] = []
    for field_name, value in metadata.items():
        if not isinstance(value, str):
            continue
        for marker in PDF_INJECTION_MARKERS:
            if marker in value:
                injected_fields.append(field_name)
                break
    return injected_fields


# ── Injection pattern catalog ─────────────────────────────────────────────

INJECTION_PATTERNS: list[tuple[str, str]] = [
    # 1. Instruction override
    (
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|commands|directives|prompts?)",
        "ignore_previous_instructions",
    ),
    # 2. Forget all knowledge
    (
        r"forget\s+(everything|all)\s+(you\s+)?(know|learned|have)",
        "forget_knowledge",
    ),
    # 3. Role assumption
    (
        r"you\s+(are\s+)?(now|must\s+act\s+as|will\s+act\s+as)\s+",
        "role_assumption",
    ),
    # 4. Secret/key extraction
    (
        r"output\s+(the\s+)?(password|key|token|secret|flag|api[-_\s]?key)",
        "secret_extraction",
    ),
    # 5. System prompt reference
    (
        r"(system\s+(prompt|message|instruction))",
        "system_prompt_reference",
    ),
    # 6. Chat template markers (Jinja2-style)
    (
        r"<\|im_start\|>|<\|im_end\|>",
        "chat_template_marker",
    ),
    # 7. Instruction markers
    (
        r"\[\s*(INST|SYS|SYSTEM)\s*\]",
        "instruction_marker",
    ),
    # 8. Markdown section injection
    (
        r"###\s*(system|user|assistant|instruction)",
        "markdown_section_injection",
    ),
    # 9. Base64 / encoded payload indicator
    (
        r"(begin\s+base64|base64\s+encoded|decode\s+and\s+execute)",
        "base64_payload",
    ),
    # 10. Delimiter injection
    (
        r"[-=]{3,}\s*(begin|end)\b",
        "delimiter_injection",
    ),
    # 11. Direct command: "Say '...'"
    (
        r"say\s+['\"].+['\"]\s*(and|without|then)",
        "direct_command",
    ),
    # 12. DAN / Jailbreak patterns
    (
        r"(DAN|jailbreak|do\s+anything\s+now|unlimited\s+mode)",
        "jailbreak_attempt",
    ),
    # 13. Unicode / RTL override attacks
    (
        r"[\u200E\u200F\u202A-\u202E\u2066-\u2069]",
        "unicode_override",
    ),
    # 14. XML / template injection
    (
        r"\{\{\s*\w+\s*\.\w+\s*\}\}|\{%\s*(include|extends|block|for|if)\s|\$\{\s*\w+\s*\}",
        "template_injection",
    ),
    # 15. SQL injection in document text
    (
        r"('\s*OR\s*'\s*'\s*=\s*'|'\s*OR\s*1\s*=\s*1|UNION\s+SELECT\s+|DROP\s+TABLE\s+|DELETE\s+FROM\s+)",
        "sql_injection",
    ),
    # 16. JSON injection
    (
        r"__proto__|prototype\s*:\s*\{|constructor\s*:\s*\{|\[\$\w+\]",
        "json_injection",
    ),
    # 17. Path traversal
    (
        r"(\.\.(\\|/))+[\w\-. ]+|file:\\/+|file:[A-Za-z]:",
        "path_traversal",
    ),
    # 18. Command injection
    (
        r"(;\s*\b(cat|ls|dir|whoami|id|pwd|echo|curl|wget|rm|mv|cp|bash|sh|powershell|cmd)\b|`[^`]+`|\$\([^)]+\))",
        "command_injection",
    ),
    # 19. XSS injection
    (
        r"<script[^>]*>.*?</script>|onerror\s*=|onload\s*=|onclick\s*=|javascript\s*:|<img[^>]+onerror|<svg[^>]+onload",
        "xss_injection",
    ),
    # 20. High-entropy encoded payload
    (
        r"[A-Za-z0-9+/]{40,}={0,2}",
        "high_entropy_encoded",
    ),
]


# ── Data types ────────────────────────────────────────────────────────────


@dataclass
class InjectionResult:
    """Result of a prompt-injection scan on a text fragment."""

    risk_score: float = 0.0
    matched_patterns: list[str] = field(default_factory=list)
    text_snippet: str = ""


# ── Detector ──────────────────────────────────────────────────────────────


class InjectionDetector:
    """Detect prompt-injection patterns in document text.

    Uses heuristic regex matching against a curated catalog of known
    injection vectors. Returns a risk score and list of matched patterns.

    Usage::

        detector = InjectionDetector()
        result = detector.evaluate("Ignore all previous instructions")
        # result.risk_score ≈ 1.0
        # result.matched_patterns == ["ignore_previous_instructions"]
    """

    def __init__(self, patterns: list[tuple[str, str]] | None = None):
        """Optionally override the default pattern catalog."""
        self._patterns = patterns or INJECTION_PATTERNS
        self._compiled: list[tuple[re.Pattern[str], str]] = [
            (re.compile(pat, re.IGNORECASE), name)
            for pat, name in self._patterns
        ]
        # Context window around the match (chars)
        self.context_window: int = 60
        # Enable extra detection layers
        self.enable_entropy_check: bool = True
        self.enable_pdf_metadata_check: bool = True

    def evaluate(self, text: str) -> InjectionResult:
        """Score *text* for injection risk.

        Args:
            text: The full document text or a text fragment to evaluate.

        Returns:
            ``InjectionResult`` with:
            - ``risk_score`` (0.0–1.0): ratio of matched patterns to total patterns
            - ``matched_patterns``: list of matched pattern names
            - ``text_snippet``: first 200 chars surrounding the first match
        """
        if not text or not text.strip():
            return InjectionResult(risk_score=0.0, matched_patterns=[], text_snippet="")

        matched_names: list[str] = []
        first_snippet: str = ""

        for compiled_re, name in self._compiled:
            match = compiled_re.search(text)
            if match:
                matched_names.append(name)
                if not first_snippet:
                    # Capture context around the first match
                    start = max(0, match.start() - self.context_window)
                    end = min(len(text), match.end() + self.context_window)
                    first_snippet = text[start:end]

        # Risk score: ratio of matched unique patterns to total
        if not self._patterns:
            risk_score = 0.0
        else:
            risk_score = len(matched_names) / len(self._patterns)

        # Entropy-based detection
        if self.enable_entropy_check:
            high_entropy_segments = scan_high_entropy(text)
            if high_entropy_segments:
                matched_names.append("high_entropy_payload")
                if not first_snippet:
                    seg = high_entropy_segments[0]
                    first_snippet = seg["snippet"]

        # Cap at first 200 chars for the snippet
        if len(first_snippet) > 200:
            first_snippet = first_snippet[:200] + "..."

        return InjectionResult(
            risk_score=min(risk_score, 1.0),
            matched_patterns=matched_names,
            text_snippet=first_snippet,
        )

    def evaluate_blocks(
        self, text_blocks: list[dict[str, Any]]
    ) -> list[InjectionResult]:
        """Evaluate each text block independently.

        Useful for per-block injection risk analysis.

        Args:
            text_blocks: List of text block dicts with a ``content`` key.

        Returns:
            List of ``InjectionResult``, one per block.
        """
        from typing import Any
        results: list[InjectionResult] = []
        for block in text_blocks:
            content = block.get("content", "")
            results.append(self.evaluate(content))
        return results

    def evaluate_pdf_metadata(
        self, metadata: dict[str, str]
    ) -> InjectionResult:
        """Evaluate PDF metadata fields for injection.

        Scans standard PDF Info dict fields (Title, Author, Subject, etc.)
        for PDF object markers or injection payloads embedded in metadata.

        Args:
            metadata: Dict of metadata fields, e.g. ``{"/Title": "...", "/Author": "..."}``.

        Returns:
            ``InjectionResult`` with risk_score and matched patterns.
        """
        if not self.enable_pdf_metadata_check:
            return InjectionResult()

        injected = scan_pdf_metadata_injection(metadata)
        if injected:
            return InjectionResult(
                risk_score=min(len(injected) / 5.0, 1.0),
                matched_patterns=[f"pdf_metadata_injection:{f}" for f in injected],
                text_snippet=f"Injected fields: {', '.join(injected)[:200]}",
            )
        return InjectionResult()


__all__ = [
    "INJECTION_PATTERNS",
    "INJECTION_PATTERNS_EXTENDED",
    "PDF_INJECTION_MARKERS",
    "HIGH_ENTROPY_THRESHOLD",
    "shannon_entropy",
    "scan_high_entropy",
    "scan_pdf_metadata_injection",
    "InjectionDetector",
    "InjectionResult",
]
