# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Global DocMirror settings — YAML defaults with env overrides."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


def _yaml_get(path: str, default: Any = None) -> Any:
    try:
        from docmirror.configs.runtime.yaml_loader import config_loader

        return config_loader.get(path, default)
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("[Config] Invalid %s=%r; using %s", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return raw.strip()


@dataclass
class OCRHyperParams:
    """
    Physically justified OCR preprocessing hyperparameters.

    Every value here has a documented rationale. Changing any value
    should require updating the justification — enforcing Deutsch's
    'hard to vary' principle.
    """

    upscale_threshold_low: int = 500
    upscale_threshold_mid: int = 1000
    upscale_factor_low: float = 4.0
    upscale_factor_mid: float = 2.0
    dark_image_brightness_threshold: int = 80
    dark_image_gamma: float = 0.6
    low_contrast_std_threshold: float = 25.0
    histogram_percentile_lo: float = 1.0
    histogram_percentile_hi: float = 99.0
    red_hue_range_1: tuple = (0, 10)
    red_hue_range_2: tuple = (160, 180)
    red_saturation_min: int = 70
    red_value_min: int = 50
    row_overlap_ratio: float = 0.4
    line_merge_v_overlap_ratio: float = 0.5
    line_merge_h_gap_multiplier: float = 1.5
    nms_overlap_threshold: float = 0.6
    min_words_initial_pass: int = 10
    min_words_final: int = 3
    dpi_passes: tuple = (150, 200, 300)
    kmeans_clusters: int = 3
    hue_tolerance: int = 15


@dataclass
class DocMirrorSettings:
    """Global configuration for DocMirror."""

    default_enhance_mode: str = "standard"
    max_pages: int = 200
    max_page_concurrency: int = 1
    ocr_dpi: int = 150
    ocr_retry_dpi: int = 300
    ocr_language: str = "auto"
    validator_pass_threshold: float = 0.7
    log_level: str = "INFO"
    fail_strategy: str = "skip"
    layout_model_path: str | None = None
    reading_order_model_path: str | None = None
    formula_model_path: str | None = None
    model_render_dpi: int = 200
    ocr_params: OCRHyperParams = field(default_factory=OCRHyperParams)
    min_file_size: int = 512
    max_file_size: int = 500_000_000
    min_image_dimension: int = 50
    table_rapid_max_pages: int | None = None
    table_rapid_min_confidence_threshold: float = 0.3
    external_ocr_quality_threshold: int = 80
    external_ocr_provider: str | None = None

    @classmethod
    def from_env(cls) -> DocMirrorSettings:
        """Load settings: env vars override docmirror.yaml defaults."""
        business = _yaml_get("business", {}) or {}
        physics = _yaml_get("physics", {}) or {}
        ocr_cfg = _yaml_get("ocr", {}) or {}
        layout_cfg = _yaml_get("layout", {}) or {}
        logging_cfg = _yaml_get("logging", {}) or {}

        from docmirror.configs.runtime.performance import resolve_max_page_concurrency

        max_conc = resolve_max_page_concurrency()

        ext_ocr = ocr_cfg.get("external") if isinstance(ocr_cfg.get("external"), dict) else {}

        instance = cls(
            default_enhance_mode=_env_str(
                "DOCMIRROR_ENHANCE_MODE",
                str(business.get("enhance_mode", "standard")),
            ),
            max_pages=_env_int("DOCMIRROR_MAX_PAGES", int(business.get("max_pages", 200))),
            max_page_concurrency=max_conc,
            ocr_dpi=int(layout_cfg.get("render_dpi", 150)),
            validator_pass_threshold=_env_float(
                "DOCMIRROR_VALIDATOR_THRESHOLD",
                float(business.get("validator_pass_threshold", 0.7)),
            ),
            log_level=_env_str("DOCMIRROR_LOG_LEVEL", str(logging_cfg.get("level", "INFO"))),
            fail_strategy=_env_str(
                "DOCMIRROR_FAIL_STRATEGY",
                str(business.get("fail_strategy", "skip")),
            ),
            model_render_dpi=int(layout_cfg.get("render_dpi", 200)),
            min_file_size=int(business.get("min_file_size", 512)),
            max_file_size=int(business.get("max_file_size", 500_000_000)),
            external_ocr_quality_threshold=_env_int(
                "DOCMIRROR_EXTERNAL_OCR_QUALITY_THRESHOLD",
                int(ocr_cfg.get("quality_threshold", 80)),
            ),
            external_ocr_provider=(
                (v := os.getenv("DOCMIRROR_EXTERNAL_OCR_PROVIDER", "").strip()) or None
            ),
        )

        rapid_pages_env = os.getenv("DOCMIRROR_TABLE_RAPID_MAX_PAGES", "").strip()
        if rapid_pages_env:
            instance.table_rapid_max_pages = int(rapid_pages_env)
        instance.table_rapid_min_confidence_threshold = _env_float(
            "DOCMIRROR_TABLE_RAPID_MIN_CONFIDENCE_THRESHOLD",
            instance.table_rapid_min_confidence_threshold,
        )

        if physics.get("ocr_upscale_threshold"):
            instance.ocr_params.upscale_threshold_low = int(physics["ocr_upscale_threshold"])

        logger.info(
            "[Config] Initialized global settings: enhance_mode='%s', "
            "max_concurrency=%d, fail_strategy='%s' (yaml+env)",
            instance.default_enhance_mode,
            instance.max_page_concurrency,
            instance.fail_strategy,
        )
        return instance

    def to_dict(self) -> dict[str, Any]:
        return {
            "enhance_mode": self.default_enhance_mode,
            "SceneDetector": {},
            "Validator": {"pass_threshold": self.validator_pass_threshold},
        }


default_settings = DocMirrorSettings.from_env()
