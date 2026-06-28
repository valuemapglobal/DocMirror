# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Tesseract OCR Backend — 80+ Languages OCR via Tesseract.
=============================================================

Provides a Tesseract-based OCR backend for scanned documents with
support for 100+ languages. Integrates with DocMirror's existing
OCR pipeline via the OCR backend protocol.

Usage::

    from docmirror.structure.ocr.backends.tesseract import TesseractBackend

    backend = TesseractBackend()
    result = backend.ocr(image, lang="eng+fra")

Supported languages: https://tesseract-ocr.github.io/tessdoc/Data-Files.html
(100+ languages available via Tesseract language packs)
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TesseractOCRResult:
    """Single element extracted by Tesseract OCR."""

    text: str = ""
    confidence: float = 0.0
    bbox: list[float] | None = None
    block_num: int = 0
    line_num: int = 0
    word_num: int = 0


@dataclass
class TesseractPageResult:
    """Full page OCR result from Tesseract."""

    text: str = ""
    words: list[TesseractOCRResult] = field(default_factory=list)
    lines: list[TesseractOCRResult] = field(default_factory=list)
    blocks: list[TesseractOCRResult] = field(default_factory=list)
    confidence: float = 0.0
    language: str = "eng"
    duration_ms: float = 0.0


# ── Language support ──────────────────────────────────────────────────────

# Major language groups mapped to Tesseract language codes
LANGUAGE_GROUPS: dict[str, list[str]] = {
    "european": [
        "eng", "fra", "deu", "ita", "spa", "por", "nld", "rus",
        "ces", "pol", "swe", "dan", "fin", "nor", "hun", "ron",
        "cat", "glg", "eus", "bel", "bul", "hrv", "slk", "slv",
        "srp", "ukr", "ell", "tur",
    ],
    "asian": [
        "chi_sim", "chi_tra", "jpn", "kor", "tha", "vie",
        "hin", "ben", "tam", "tel", "kan", "mal", "guj", "pan",
        "urd", "mar", "nep", "sin", "mya", "khm", "lao",
    ],
    "middle_east": [
        "ara", "heb", "fas", "kur", "pus",
    ],
    "other": [
        "amh", "aze", "est", "lav", "lit", "mkd", "mlt",
        "sqi", "tat", "uzb",
    ],
}

# Full flat list of all supported languages
ALL_TESSERACT_LANGUAGES: list[str] = sorted(
    set().union(*LANGUAGE_GROUPS.values())
)


def get_installed_languages() -> list[str]:
    """Return list of Tesseract languages installed on this system.

    Runs ``tesseract --list-langs`` to discover available language packs.
    On some systems output goes to stdout, on others to stderr.
    """
    import subprocess
    try:
        result = subprocess.run(
            ["tesseract", "--list-langs"],
            capture_output=True, text=True, timeout=10,
        )
        # Output may go to stdout or stderr depending on version
        raw = result.stdout or result.stderr or ""
        lines = raw.strip().split("\n")
        # Output format: "List of available languages (N):" then each lang on its own line
        langs = [
            line.strip()
            for line in lines
            if line.strip()
            and not line.startswith("List")
            and not line.startswith("script/")
        ]
        return langs
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        logger.warning("Could not list Tesseract languages: %s", exc)
        return []


# ── TesseractBackend ──────────────────────────────────────────────────────


class TesseractBackend:
    """Tesseract-based OCR backend supporting 100+ languages.

    Attributes:
        languages: Set of supported language codes (auto-detected from system).
        tesseract_cmd: Path to the tesseract binary (auto-detected).
        have_pytesseract: Whether pytesseract is installed.
    """

    def __init__(self, tesseract_cmd: str | None = None):
        self.tesseract_cmd = tesseract_cmd or shutil.which("tesseract") or "tesseract"
        self._installed_langs: list[str] | None = None

        # Check pytesseract availability
        try:
            import pytesseract  # noqa: F401
            self.have_pytesseract = True
        except ImportError:
            self.have_pytesseract = False

    @property
    def name(self) -> str:
        return "tesseract"

    @property
    def is_available(self) -> bool:
        if not self.have_pytesseract:
            return False
        try:
            return shutil.which("tesseract") is not None
        except Exception:
            return False

    @property
    def installed_languages(self) -> list[str]:
        """Return list of installed Tesseract language packs."""
        if self._installed_langs is None:
            self._installed_langs = get_installed_languages()
        return self._installed_langs

    @property
    def supported_languages(self) -> list[str]:
        """Return list of all languages this backend could support (if installed)."""
        return ALL_TESSERACT_LANGUAGES

    def ocr(
        self,
        image_bytes: bytes,
        *,
        lang: str = "eng",
        config: str | None = None,
        psm: int = 3,
        timeout: int = 60,
    ) -> TesseractPageResult:
        """Run Tesseract OCR on an image.

        Args:
            image_bytes: PNG or JPEG bytes of the image to OCR.
            lang: Tesseract language code(s), e.g. ``"eng"``, ``"chi_sim+eng"``.
            config: Additional Tesseract config string.
            psm: Page segmentation mode (3=auto, 6=block, 7=single line, etc.).
            timeout: Timeout in seconds for Tesseract.

        Returns:
            ``TesseractPageResult`` with extracted text and per-word data.
        """
        import time

        import pytesseract
        from PIL import Image
        import io

        if not self.have_pytesseract:
            raise RuntimeError(
                "pytesseract is not installed. Install with: pip install pytesseract"
            )

        if not shutil.which("tesseract"):
            raise RuntimeError(
                "Tesseract binary not found. Install Tesseract OCR engine."
            )

        # Validate requested language(s)
        installed = self.installed_languages
        requested_langs = [l.strip() for l in lang.split("+")]
        if installed and not all(l in installed for l in requested_langs):
            missing = [l for l in requested_langs if l not in installed]
            logger.warning(
                "Tesseract language(s) not installed: %s. "
                "Installed: %s. Falling back to available languages.",
                missing, installed,
            )
            # Filter to only installed languages
            valid_langs = [l for l in requested_langs if l in installed]
            if not valid_langs:
                logger.warning("No valid languages. Using 'eng'.")
                valid_langs = ["eng"]
            lang = "+".join(valid_langs)

        start = time.time()

        try:
            # Open image from bytes
            img = Image.open(io.BytesIO(image_bytes))

            custom_config = config or f"--psm {psm}"

            # Get full text
            text = pytesseract.image_to_string(
                img, lang=lang, config=custom_config, timeout=timeout,
            )

            # Get per-word data with bounding boxes
            word_data = pytesseract.image_to_data(
                img, lang=lang, config=custom_config, output_type=pytesseract.Output.DICT,
                timeout=timeout,
            )

            # Get per-block confidence
            confidence = self._compute_confidence(word_data)

            duration = (time.time() - start) * 1000

            # Build structured result
            words: list[TesseractOCRResult] = []
            lines: list[TesseractOCRResult] = []
            blocks: list[TesseractOCRResult] = []

            n = len(word_data.get("text", []))
            current_line_num = -1
            current_line_text = ""
            current_line_conf_sum = 0.0
            current_line_conf_count = 0
            current_line_bbox: list[float] | None = None

            for i in range(n):
                word_text = word_data.get("text", [""])[i]
                word_conf = int(word_data.get("conf", [0])[i]) / 100.0
                block_num = int(word_data.get("block_num", [0])[i])
                line_num = int(word_data.get("line_num", [0])[i])
                par_num = int(word_data.get("par_num", [0])[i])
                left = int(word_data.get("left", [0])[i])
                top = int(word_data.get("top", [0])[i])
                width = int(word_data.get("width", [0])[i])
                height = int(word_data.get("height", [0])[i])

                if not word_text.strip():
                    continue

                word_bbox = [left, top, left + width, top + height]

                words.append(TesseractOCRResult(
                    text=word_text,
                    confidence=word_conf,
                    bbox=word_bbox,
                    block_num=block_num,
                    line_num=line_num,
                    word_num=i,
                ))

                # Accumulate line
                if line_num != current_line_num:
                    if current_line_text.strip():
                        lines.append(TesseractOCRResult(
                            text=current_line_text.strip(),
                            confidence=current_line_conf_sum / max(current_line_conf_count, 1),
                            bbox=current_line_bbox,
                        ))
                    current_line_num = line_num
                    current_line_text = ""
                    current_line_conf_sum = 0.0
                    current_line_conf_count = 0
                    current_line_bbox = None

                current_line_text += word_text + " "
                current_line_conf_sum += word_conf
                current_line_conf_count += 1
                if current_line_bbox is None:
                    current_line_bbox = list(word_bbox) if word_bbox else None

            # Flush last line
            if current_line_text.strip():
                lines.append(TesseractOCRResult(
                    text=current_line_text.strip(),
                    confidence=current_line_conf_sum / max(current_line_conf_count, 1),
                    bbox=current_line_bbox,
                ))

            return TesseractPageResult(
                text=text.strip(),
                words=words,
                lines=lines,
                blocks=blocks,
                confidence=confidence,
                language=lang,
                duration_ms=round(duration, 2),
            )

        except Exception as exc:
            logger.error("Tesseract OCR failed: %s", exc)
            raise

    def ocr_to_dict(self, image_bytes: bytes, **kwargs) -> dict[str, Any]:
        """Run OCR and return result as a plain dict (for serialization)."""
        result = self.ocr(image_bytes, **kwargs)
        return {
            "text": result.text,
            "confidence": result.confidence,
            "language": result.language,
            "duration_ms": result.duration_ms,
            "word_count": len(result.words),
            "line_count": len(result.lines),
        }

    @staticmethod
    def _compute_confidence(word_data: dict[str, Any]) -> float:
        """Compute average confidence from Tesseract word-level data."""
        confs = [
            int(conf) / 100.0
            for conf in word_data.get("conf", [])
            if int(conf) >= 0  # Tesseract uses -1 for non-word elements
        ]
        if not confs:
            return 0.0
        return sum(confs) / len(confs)


__all__ = [
    "TesseractBackend",
    "TesseractPageResult",
    "TesseractOCRResult",
    "ALL_TESSERACT_LANGUAGES",
    "LANGUAGE_GROUPS",
    "get_installed_languages",
]
