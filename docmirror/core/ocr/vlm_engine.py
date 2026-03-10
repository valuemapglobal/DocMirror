"""
VLM Inference Engine
=====================================

VLM inference engine based on Ollama HTTP API.
Supports Qwen2.5-VL models for document page understanding.

Core API:
    - page_to_markdown:    Page image → complete Markdown (text + tables + formulas)
    - recognize_table:     Table region image → HTML <table>
    - recognize_formula:   Formula region image → LaTeX
    - is_available:        Check if Ollama service is available

Design principles:
    - Async HTTP (httpx), non-blocking event loop
    - Timeout retry: default 120s timeout, auto-fallback to pipeline on failure
    - Zero-intrusion: Pipeline auto-degrades when VLM unavailable
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── Default configuration ──
_DEFAULT_MODEL = "qwen2.5vl:3b"
_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_TIMEOUT = 600  # seconds (CPU inference is slow, needs ample time)
_DEFAULT_TEMPERATURE = 0.1  # Low temperature = high determinism


# ═══════════════════════════════════════════════════════════════════════════════
# Prompt Templates (optimized for OmniDocBench benchmark metrics)
# ═══════════════════════════════════════════════════════════════════════════════

PROMPT_PAGE_TO_MARKDOWN = """Convert this document page to Markdown format. Rules:
1. Plain text paragraphs as-is, preserve paragraph structure
2. Headings: use # ## ### for title hierarchy
3. Tables: output as HTML <table><thead><tbody><tr><th><td> with colspan/rowspan if merged cells exist
4. Math formulas: inline $...$ and display $$...$$, output LaTeX
5. Maintain original reading order (left-to-right, top-to-bottom, column by column)
6. Do NOT add any explanation, commentary, or description
7. Output ONLY the converted Markdown content"""

PROMPT_TABLE_TO_HTML = """Convert this table image to HTML format.
Rules:
1. Use <table><thead><tbody><tr><th><td> structure
2. Detect and include colspan/rowspan for merged cells
3. Preserve all cell text exactly as shown
4. Output ONLY the HTML table, no other text"""

PROMPT_FORMULA_TO_LATEX = """Convert this mathematical formula to LaTeX.
Rules:
1. Output ONLY the LaTeX code, no $$ delimiters
2. Use standard LaTeX commands
3. Be precise with subscripts, superscripts, fractions, etc.
4. Output ONLY the LaTeX, no explanation"""


class VLMEngine:
    """Qwen2.5-VL inference engine (via Ollama HTTP API).

    Async interface: each call sends one image + prompt, returns model output.
    When Ollama is unavailable, all methods degrade gracefully (return None).

    Usage::

        engine = VLMEngine()
        if engine.is_available():
            md = await engine.page_to_markdown(image_bytes)
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = _DEFAULT_TIMEOUT,
        temperature: float = _DEFAULT_TEMPERATURE,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.temperature = temperature
        self._available: Optional[bool] = None  # Cache availability state

        # Ensure localhost bypasses system proxy (httpx on macOS intercepts it)
        import os
        no_proxy = os.environ.get("NO_PROXY", "")
        if "localhost" not in no_proxy:
            os.environ["NO_PROXY"] = f"{no_proxy},localhost,127.0.0.1" if no_proxy else "localhost,127.0.0.1"
            os.environ["no_proxy"] = os.environ["NO_PROXY"]

    # ───────────────────────────────────────────────────────────────────────
    # 可用性检查
    # ───────────────────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Check if Ollama service is available (Sync, 带Cache)。"""
        if self._available is not None:
            return self._available

        try:
            import httpx
            resp = httpx.get(
                f"{self.base_url}/api/tags",
                timeout=5.0,
                proxy=None,
            )
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                self._available = any(self.model in m for m in models)
                if self._available:
                    logger.info(f"[VLM] Ollama Ready: model={self.model}")
                else:
                    logger.warning(
                        f"[VLM] Ollama Running but model {self.model} not installed. "
                        f"Available models: {models}"
                    )
            else:
                self._available = False
        except Exception as e:
            logger.debug(f"[VLM] Ollama Unavailable: {e}")
            self._available = False

        return self._available

    # ───────────────────────────────────────────────────────────────────────
    # 核心InferenceMethod
    # ───────────────────────────────────────────────────────────────────────

    async def _call_ollama(
        self,
        prompt: str,
        image_bytes: bytes,
        *,
        max_tokens: int = 8192,
    ) -> Optional[str]:
        """Low-level Ollama API call.

        Args:
            prompt: Text prompt
            image_bytes: Image binary data (PNG/JPEG)
            max_tokens: Maximum output tokens

        Returns:
            Model output text, returns None on failure
        """
        try:
            import httpx
        except ImportError:
            logger.error("[VLM] httpx not installed, please run: pip install httpx")
            return None

        # Encode image to base64
        img_b64 = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": max_tokens,
            },
        }

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.timeout, proxy=None) as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                )

            elapsed = time.monotonic() - t0

            if resp.status_code != 200:
                logger.warning(
                    f"[VLM] Ollama Returns {resp.status_code}: "
                    f"{resp.text[:200]}"
                )
                return None

            data = resp.json()
            response_text = data.get("response", "")

            # Statistics
            eval_count = data.get("eval_count", 0)
            speed = eval_count / elapsed if elapsed > 0 else 0
            logger.info(
                f"[VLM] Inference complete: {eval_count} tokens, "
                f"{elapsed:.1f}s, {speed:.1f} tok/s"
            )

            return response_text

        except httpx.TimeoutException:
            elapsed = time.monotonic() - t0
            logger.warning(f"[VLM] Inference timeout ({elapsed:.1f}s > {self.timeout}s)")
            return None
        except Exception as e:
            logger.warning(f"[VLM] Inference error: {e}")
            return None

    # ───────────────────────────────────────────────────────────────────────
    # 高级 API
    # ───────────────────────────────────────────────────────────────────────

    async def page_to_markdown(self, image_bytes: bytes) -> Optional[str]:
        """Page image → complete Markdown (text + HTML tables + LaTeX formulas).

        Core benchmarking method: single call handles all text/table/formula recognition.

        Args:
            image_bytes: Page rendered image (PNG/JPEG), recommended 200-300 DPI

        Returns:
            Markdown string, returns None on failure
        """
        return await self._call_ollama(
            PROMPT_PAGE_TO_MARKDOWN, image_bytes, max_tokens=8192
        )

    async def recognize_table(self, image_bytes: bytes) -> Optional[str]:
        """Table region image → HTML <table> 结构。

        Used for VLM-based re-recognition when pipeline table quality is poor.

        Returns:
            HTML table string, returns None on failure
        """
        return await self._call_ollama(
            PROMPT_TABLE_TO_HTML, image_bytes, max_tokens=4096
        )

    async def recognize_formula(self, image_bytes: bytes) -> Optional[str]:
        """Formula region image → LaTeX 字符串。

        Returns:
            LaTeX string (without $$ delimiters), returns None on failure
        """
        return await self._call_ollama(
            PROMPT_FORMULA_TO_LATEX, image_bytes, max_tokens=1024
        )

    # ───────────────────────────────────────────────────────────────────────
    # Utility methods
    # ───────────────────────────────────────────────────────────────────────

    def render_page_to_image(self, pdf_path, page_idx: int = 0, dpi: int = 216) -> Optional[bytes]:
        """Render a PDF page to PNG image.

        Args:
            pdf_path: PDF file path
            page_idx: Page index (0-based)
            dpi: Render DPI (216 = 3x standard 72dpi, balancing quality and speed)

        Returns:
            PNG bytes, returns None on failure
        """
        try:
            import fitz
            doc = fitz.open(str(pdf_path))
            if page_idx >= len(doc):
                return None
            page = doc[page_idx]
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            return pix.tobytes("png")
        except Exception as e:
            logger.warning(f"[VLM] Page rendering failed: {e}")
            return None
