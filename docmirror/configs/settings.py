"""
DocMirror Global Settings
=========================

Centralized system-level configuration for the DocMirror parsing engine.

All settings have sensible defaults and can be overridden via environment
variables using the ``DOCMIRROR_`` prefix. The ``from_env()`` classmethod
reads the current environment and returns a configured instance.

Configuration groups:
    - **Enhancement**: Default pipeline mode and LLM integration toggle.
    - **Performance**: Page limits, OCR resolution, and language detection.
    - **Validation**: Pass/fail thresholds for the quality validator.
    - **Model paths**: Optional paths to AI model weights (layout, reading
      order, formula recognition). When ``None``, rule-based fallbacks
      are used instead.
    - **Pipeline strategy**: How to handle middleware failures (skip vs abort).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class DocMirrorSettings:
    """
    Global configuration for DocMirror.

    Instantiate directly with custom values, or use ``from_env()`` to
    load from environment variables. Use ``to_dict()`` to inject into
    the Orchestrator pipeline configuration.
    """

    # ── Enhancement settings ──
    default_enhance_mode: str = "standard"  # "raw" | "standard" | "full"

    # ── LLM integration ──
    enable_llm: bool = False        # Whether to use LLM-powered validation/repair
    llm_model: str = "qwen-vl-max"  # LLM model name (passed to VLM adapter)
    llm_max_tokens: int = 4096      # Maximum tokens per LLM request
    llm_temperature: float = 0.0    # LLM temperature (0.0 for deterministic output)

    # ── Performance limits ──
    max_pages: int = 200       # Maximum pages to process per document
    ocr_dpi: int = 150         # Default DPI for rendering pages to images for OCR
    ocr_retry_dpi: int = 300   # Higher DPI used when initial OCR produces poor results
    ocr_language: str = "auto" # "auto" = auto-detect; or specify e.g. "zh", "en"

    # ── Validation thresholds ──
    validator_pass_threshold: float = 0.7  # Minimum score to consider parsing successful

    # ── Logging ──
    log_level: str = "INFO"

    # ── Pipeline error handling ──
    fail_strategy: str = "skip"  # "skip" = ignore failed middlewares; "abort" = halt pipeline

    # ── Optional AI model file paths ──
    # When None, DocMirror uses rule-based fallbacks instead of AI models
    layout_model_path: Optional[str] = None        # DocLayout-YOLO ONNX model path
    reading_order_model_path: Optional[str] = None  # LayoutReader ONNX model path
    formula_model_path: Optional[str] = None        # Pix2Tex / UniMERNet ONNX model path

    # ── Model inference parameters ──
    model_render_dpi: int = 200  # DPI for rendering pages before DocLayout-YOLO inference

    @classmethod
    def from_env(cls) -> DocMirrorSettings:
        """
        Create a DocMirrorSettings instance from environment variables.

        Reads ``DOCMIRROR_*`` environment variables and falls back to
        default values when variables are not set.

        Supported env vars:
            DOCMIRROR_ENHANCE_MODE       → default_enhance_mode
            DOCMIRROR_ENABLE_LLM         → enable_llm (true/false)
            DOCMIRROR_LLM_MODEL          → llm_model
            DOCMIRROR_MAX_PAGES          → max_pages
            DOCMIRROR_VALIDATOR_THRESHOLD → validator_pass_threshold
            DOCMIRROR_LOG_LEVEL          → log_level
            DOCMIRROR_FAIL_STRATEGY      → fail_strategy
        """
        return cls(
            default_enhance_mode=os.getenv("DOCMIRROR_ENHANCE_MODE", "standard"),
            enable_llm=os.getenv("DOCMIRROR_ENABLE_LLM", "false").lower() == "true",
            llm_model=os.getenv("DOCMIRROR_LLM_MODEL", "qwen-vl-max"),
            max_pages=int(os.getenv("DOCMIRROR_MAX_PAGES", "200")),
            validator_pass_threshold=float(os.getenv("DOCMIRROR_VALIDATOR_THRESHOLD", "0.7")),
            log_level=os.getenv("DOCMIRROR_LOG_LEVEL", "INFO"),
            fail_strategy=os.getenv("DOCMIRROR_FAIL_STRATEGY", "skip"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert settings to a dict suitable for Orchestrator config injection.

        Returns a dict keyed by middleware class name, with each value
        containing the relevant configuration subset for that middleware.
        """
        return {
            "enhance_mode": self.default_enhance_mode,
            "SceneDetector": {"enable_llm": self.enable_llm},
            "ColumnMapper": {},
            "Validator": {"pass_threshold": self.validator_pass_threshold},
            "Repairer": {"enable_llm": self.enable_llm},
        }


# Module-level singleton: initialized once from environment variables
# at import time. Can be overridden by creating a new instance.
default_settings = DocMirrorSettings.from_env()
