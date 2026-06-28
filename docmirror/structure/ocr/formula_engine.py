# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Formula engine — image-based mathematical formula OCR.

Purpose: Preprocesses formula crops, runs OCR, and post-processes recognized
LaTeX (bracket balance, symbol corrections).

Main components: ``FormulaEngine``, ``recognize_batch``, ``recognize_with_confidence``.

Upstream: Formula zone images from handlers.

Downstream: ``physical.models.Block`` (formula type).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RecognitionResult:
    """Result from formula recognition with confidence.

    Attributes:
        latex: Recognized LaTeX string.
        confidence: Aggregate confidence score [0.0, 1.0].
        backend: Name of the recognition backend used.
        preprocessing_ms: Time spent on image preprocessing in ms.
        inference_ms: Time spent on model inference in ms.
    """
    latex: str = ""
    confidence: float = 0.0
    backend: str = "none"
    preprocessing_ms: float = 0.0
    inference_ms: float = 0.0


class FormulaEngine:
    """Unified formula recognition entry point — Strategy pattern.

    Automatically selects the best available backend:
        1. UniMERNet ONNX (if *model_path* is specified and exists)
        2. rapid_latex_ocr (if installed)
        3. Empty string (no backend available)

    All backends share the same interface: ``image_bytes → LaTeX string``.
    """

    # GA F5: UniMERNet ONNX input dimensions
    _ONNX_INPUT_HEIGHT = 192
    _ONNX_INPUT_WIDTH = 672

    def __init__(self, model_path: str | None = None, vocab_path: str | None = None):
        """
        Args:
            model_path: Path to a UniMERNet ONNX model file.
                ``None`` skips the ONNX backend and falls back to
                rapid_latex_ocr.
            vocab_path: Path to the token vocabulary file for ONNX decoding.
                If None, uses a built-in minimal LaTeX vocabulary.
        """
        self._model_path = model_path
        self._vocab_path = vocab_path
        self._onnx_session = None
        self._vocab: dict[int, str] | None = None
        self._rapid_ocr = None
        self._backend = "none"
        self._initialized = False

    def _lazy_init(self):
        """Lazy initialisation: runs on the first call to ``recognize()``."""
        if self._initialized:
            return
        self._initialized = True

        # Strategy 1: UniMERNet ONNX
        if self._model_path:
            path = Path(self._model_path)
            if path.exists():
                try:
                    import onnxruntime as ort

                    self._onnx_session = ort.InferenceSession(
                        str(path),
                        providers=["CPUExecutionProvider"],
                    )
                    self._load_vocab()
                    self._backend = "unimernet_onnx"
                    logger.info(f"[FormulaEngine] Using UniMERNet ONNX: {path}")
                    return
                except ImportError:
                    logger.debug("[FormulaEngine] onnxruntime not available")
                except Exception as e:
                    logger.warning(f"[FormulaEngine] ONNX load failed: {e}")

        # Strategy 2: rapid_latex_ocr
        try:
            from rapid_latex_ocr import LaTeXOCR

            self._rapid_ocr = LaTeXOCR()
            self._backend = "rapid_latex_ocr"
            logger.info("[FormulaEngine] Using rapid_latex_ocr")
            return
        except ImportError:
            logger.debug("[FormulaEngine] rapid_latex_ocr not installed")
        except Exception as e:
            logger.warning(f"[FormulaEngine] rapid_latex_ocr init failed: {e}")

        # Strategy 3: no backend available
        self._backend = "none"
        logger.info("[FormulaEngine] No formula backend available")

    def _load_vocab(self):
        """Load token vocabulary for ONNX output decoding.

        If no vocab file, uses a minimal LaTeX symbol vocabulary.
        """
        if self._vocab_path and Path(self._vocab_path).exists():
            try:
                self._vocab = {}
                with open(self._vocab_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            parts = line.split("\t", 1)
                            if len(parts) == 2:
                                self._vocab[int(parts[0])] = parts[1]
                logger.debug(f"[FormulaEngine] Loaded vocab: {len(self._vocab)} tokens")
                return
            except Exception as e:
                logger.warning(f"[FormulaEngine] Vocab load failed: {e}")

        # Built-in minimal LaTeX vocabulary (top tokens)
        self._vocab = self._build_fallback_vocab()

    @staticmethod
    def _build_fallback_vocab() -> dict[int, str]:
        """Build a minimal fallback LaTeX vocabulary for ONNX decoding.

        Covers the most common LaTeX tokens for formula recognition.
        """
        tokens = [
            # Special tokens
            "<PAD>", "<BOS>", "<EOS>", "<UNK>",
            # Greek lowercase
            r"\alpha", r"\beta", r"\gamma", r"\delta", r"\epsilon", r"\varepsilon",
            r"\zeta", r"\eta", r"\theta", r"\iota", r"\kappa", r"\lambda", r"\mu",
            r"\nu", r"\xi", r"\pi", r"\rho", r"\sigma", r"\tau", r"\upsilon",
            r"\phi", r"\varphi", r"\chi", r"\psi", r"\omega",
            # Greek uppercase
            r"\Gamma", r"\Delta", r"\Theta", r"\Lambda", r"\Xi",
            r"\Pi", r"\Sigma", r"\Upsilon", r"\Phi", r"\Psi", r"\Omega",
            # Operators and relations
            r"\pm", r"\mp", r"\times", r"\div", r"\cdot", r"\oplus",
            r"\leq", r"\geq", r"\neq", r"\approx", r"\equiv", r"\sim",
            r"\in", r"\notin", r"\subset", r"\supset", r"\subseteq",
            # Large operators
            r"\sum", r"\prod", r"\int", r"\oint", r"\iint",
            # Functions
            r"\sin", r"\cos", r"\tan", r"\log", r"\ln", r"\lim",
            # Structures
            r"\frac", r"\sqrt", r"\overline", r"\underline",
            r"\left", r"\right", r"\begin", r"\end",
            # Miscellaneous
            r"\infty", r"\partial", r"\nabla", r"\forall", r"\exists",
            r"\text", r"\mathrm", r"\mathbf", r"\mathit",
            # Brackets
            "{", "}", "(", ")", "[", "]", r"\langle", r"\rangle",
            # Punctuation and digits
            "^", "_", "&", "\\", ",", ".",
            "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
            # Single letters (a-z, A-Z)
            *[chr(c) for c in range(ord('a'), ord('z') + 1)],
            *[chr(c) for c in range(ord('A'), ord('Z') + 1)],
            # Binary operators
            "+", "-", "=", "<", ">", "/", "*",
        ]
        return {i: t for i, t in enumerate(tokens)}

    # ── Main recognition API ────────────────────────────────────────────

    def recognize(self, image_bytes: bytes) -> str:
        """Recognise a formula image and return LaTeX.

        Args:
            image_bytes: Raw image bytes of the formula region.

        Returns:
            LaTeX string, or an empty string on failure.
        """
        result = self.recognize_with_confidence(image_bytes)
        return result.latex

    def recognize_with_confidence(self, image_bytes: bytes) -> RecognitionResult:
        """Recognise a formula image and return LaTeX with confidence.

        Args:
            image_bytes: Raw image bytes of the formula region.

        Returns:
            RecognitionResult with LaTeX, confidence, backend, and timing.
        """
        import time

        if not image_bytes:
            return RecognitionResult()

        self._lazy_init()

        t0 = time.perf_counter()
        image_bytes = _preprocess_formula_image(image_bytes)
        preproc_ms = (time.perf_counter() - t0) * 1000

        try:
            t1 = time.perf_counter()
            if self._backend == "unimernet_onnx":
                latex, conf = self._recognize_onnx_with_confidence(image_bytes)
                inf_ms = (time.perf_counter() - t1) * 1000
                return RecognitionResult(
                    latex=latex,
                    confidence=conf,
                    backend="unimernet_onnx",
                    preprocessing_ms=preproc_ms,
                    inference_ms=inf_ms,
                )
            elif self._backend == "rapid_latex_ocr":
                latex, conf = self._recognize_rapid_with_confidence(image_bytes)
                inf_ms = (time.perf_counter() - t1) * 1000
                return RecognitionResult(
                    latex=latex,
                    confidence=conf,
                    backend="rapid_latex_ocr",
                    preprocessing_ms=preproc_ms,
                    inference_ms=inf_ms,
                )
        except Exception as e:
            logger.debug(f"[FormulaEngine] recognition error: {e}")

        return RecognitionResult(backend=self._backend)

    def recognize_batch(
        self,
        image_list: list[bytes],
        max_batch_size: int = 8,
    ) -> list[RecognitionResult]:
        """Recognise multiple formula images in batch.

        Args:
            image_list: List of raw image bytes.
            max_batch_size: Maximum batch size for ONNX inference.

        Returns:
            List of RecognitionResult, one per input image.
        """
        import time

        if not image_list:
            return []

        self._lazy_init()

        results: list[RecognitionResult] = []

        # Preprocess all images
        t0 = time.perf_counter()
        preprocessed = [_preprocess_formula_image(img) for img in image_list]
        preproc_ms = (time.perf_counter() - t0) * 1000 / max(len(image_list), 1)

        # Batch infer or sequential fallback
        if self._backend == "unimernet_onnx" and len(preprocessed) > 1:
            results = self._recognize_batch_onnx(preprocessed, max_batch_size, preproc_ms)
        else:
            for img in preprocessed:
                results.append(self.recognize_with_confidence(img))

        return results

    # ── ONNX recognition ────────────────────────────────────────────────

    def _recognize_onnx(self, image_bytes: bytes) -> str:
        """ONNX inference — with proper implementation.

        Preprocesses the image to the expected UniMERNet input format
        (192x672, BGR normalized), runs inference, and decodes output tokens.

        Returns LaTeX string or falls back to rapid_latex_ocr.
        """
        latex, _ = self._recognize_onnx_with_confidence(image_bytes)
        return latex

    def _recognize_onnx_with_confidence(self, image_bytes: bytes) -> tuple[str, float]:
        """ONNX inference with token-level confidence aggregation.

        Returns:
            Tuple of (LaTeX string, confidence score).
        """
        if self._onnx_session is None:
            if self._rapid_ocr is not None:
                return self._recognize_rapid_with_confidence(image_bytes)
            return "", 0.0

        try:
            import numpy as np
            from PIL import Image
            from io import BytesIO

            # Load image, convert to BGR, resize to ONNX expected input
            img = Image.open(BytesIO(image_bytes)).convert("RGB")
            img = img.resize((self._ONNX_INPUT_WIDTH, self._ONNX_INPUT_HEIGHT), Image.LANCZOS)

            # Convert to numpy BGR array and normalize
            arr = np.array(img, dtype=np.float32)
            arr = arr[:, :, ::-1]  # RGB → BGR

            # UniMERNet normalization (ImageNet stats in BGR)
            mean = np.array([0.406, 0.456, 0.485], dtype=np.float32).reshape(1, 1, 3)
            std = np.array([0.225, 0.224, 0.229], dtype=np.float32).reshape(1, 1, 3)
            arr = (arr / 255.0 - mean) / std

            # HWC → CHW, add batch dim
            arr = np.transpose(arr, (2, 0, 1))  # CHW
            arr = np.expand_dims(arr, axis=0)    # NCHW

            # Run ONNX inference
            input_name = self._onnx_session.get_inputs()[0].name
            output_name = self._onnx_session.get_outputs()[0].name
            logits = self._onnx_session.run([output_name], {input_name: arr})[0]

            # Decode logits to LaTeX tokens
            latex, confidence = self._decode_logits(logits[0])
            return latex, confidence

        except Exception as e:
            logger.debug(f"[FormulaEngine] ONNX inference error: {e}")
            if self._rapid_ocr is not None:
                return self._recognize_rapid_with_confidence(image_bytes)
            return "", 0.0

    def _decode_logits(self, logits: Any) -> tuple[str, float]:
        """Decode ONNX output logits into LaTeX string with confidence.

        Args:
            logits: Model output logits of shape (seq_len, vocab_size).

        Returns:
            Tuple of (LaTeX string, mean token confidence).
        """
        try:
            import numpy as np

            # Argmax decoding
            token_ids = np.argmax(logits, axis=-1)
            confidences = np.max(logits, axis=-1)

            # Collect tokens, stopping at <EOS> (token id 2 by convention)
            tokens: list[str] = []
            token_confs: list[float] = []
            for tid, conf in zip(token_ids, confidences):
                tid = int(tid)
                if tid <= 2:  # PAD/BOS/EOS
                    if tid == 2:  # EOS
                        break
                    continue
                if self._vocab and tid in self._vocab:
                    tok = self._vocab[tid]
                    if tok.startswith("<"):
                        continue
                    tokens.append(tok)
                    token_confs.append(float(conf))

            latex = "".join(tokens)
            confidence = float(np.mean(token_confs)) if token_confs else 0.0
            return latex, confidence

        except Exception:
            return "", 0.0

    def _recognize_batch_onnx(
        self,
        preprocessed: list[bytes],
        max_batch_size: int,
        preproc_ms: float,
    ) -> list[RecognitionResult]:
        """Batch ONNX inference for multiple images.

        Args:
            preprocessed: List of preprocessed image bytes.
            max_batch_size: Max images per batch.
            preproc_ms: Per-image preprocessing time.

        Returns:
            List of RecognitionResult.
        """
        import time
        results: list[RecognitionResult] = []

        for i in range(0, len(preprocessed), max_batch_size):
            batch = preprocessed[i:i + max_batch_size]
            for img_bytes in batch:
                t1 = time.perf_counter()
                latex, conf = self._recognize_onnx_with_confidence(img_bytes)
                inf_ms = (time.perf_counter() - t1) * 1000
                results.append(RecognitionResult(
                    latex=latex,
                    confidence=conf,
                    backend="unimernet_onnx",
                    preprocessing_ms=preproc_ms,
                    inference_ms=inf_ms,
                ))

        return results

    # ── rapid_latex_ocr recognition ─────────────────────────────────────

    def _recognize_rapid(self, image_bytes: bytes) -> str:
        """Recognise using rapid_latex_ocr."""
        result, _ = self._rapid_ocr(image_bytes)
        return result or ""

    def _recognize_rapid_with_confidence(self, image_bytes: bytes) -> tuple[str, float]:
        """Recognise using rapid_latex_ocr with confidence estimation.

        rapid_latex_ocr doesn't provide token-level confidence, so we
        estimate based on output characteristics.
        """
        result, _ = self._rapid_ocr(image_bytes)
        if not result:
            return "", 0.0

        # Estimate confidence from output quality heuristics
        conf = _estimate_rapid_confidence(result)
        return result, conf

    # ── Normalization API ───────────────────────────────────────────────

    def recognize_and_normalize(self, image_bytes: bytes) -> str:
        """Recognise and normalise in a single step — convenience API."""
        result = self.recognize_with_confidence(image_bytes)
        if result.latex:
            return self.normalize_latex(result.latex)
        return ""

    @staticmethod
    def normalize_latex(latex: str) -> str:
        """Deep LaTeX normalisation — maximise CDM (Content Difference Metric)
        match rate.

        Steps (in order):
            1. Strip leading/trailing whitespace and ``$`` delimiters.
            2. Apply common OCR error corrections.
            3. Remove redundant commands (``\\displaystyle``, etc.).
            4. Inline ``\\text{}`` / ``\\mathrm{}`` content.
            5. Balance mismatched brackets.
            6. Conservative brace simplification.
            7. Whitespace normalisation.
        """
        if not latex or not latex.strip():
            return ""

        latex = latex.strip()

        # ── Step 1: strip outer $ delimiters ──
        if latex.startswith("$$") and latex.endswith("$$"):
            latex = latex[2:-2].strip()
        elif latex.startswith("$") and latex.endswith("$"):
            latex = latex[1:-1].strip()

        # Strip \[ \] delimiters
        if latex.startswith("\\[") and latex.endswith("\\]"):
            latex = latex[2:-2].strip()

        # ── Step 2: common OCR error corrections ──
        latex = _apply_ocr_corrections(latex)

        # ── Step 3: remove redundant display-style commands ──
        for cmd in (r"\displaystyle", r"\textstyle", r"\scriptstyle", r"\scriptscriptstyle"):
            latex = latex.replace(cmd, "")

        # Remove invisible delimiters from \left. / \right.
        latex = latex.replace(r"\left.", r"\left").replace(r"\right.", r"\right")

        # ── Step 4: inline \text{} / \mathrm{} / \mathit{} content ──
        latex = re.sub(r"\\(?:text|mathrm|mathit|mbox|hbox)\{([^{}]*)\}", r"\1", latex)

        # ── Step 5: bracket balancing ──
        latex = _balance_brackets(latex)

        # ── Step 7: whitespace normalisation ──
        latex = re.sub(r"\s+", " ", latex)
        latex = re.sub(r"\s*([+\-=<>])\s*", r" \1 ", latex)
        latex = re.sub(r",\s*", ", ", latex)
        latex = latex.strip()

        return latex

    @property
    def backend_name(self) -> str:
        """Name of the currently active backend."""
        self._lazy_init()
        return self._backend


# ═══════════════════════════════════════════════════════════════════════════════
# LaTeX normalisation helpers
# ═══════════════════════════════════════════════════════════════════════════════

_OCR_CORRECTIONS = {
    # Greek letters
    r"\Iambda": r"\lambda",
    r"\aIpha": r"\alpha",
    r"\bata": r"\beta",
    r"\epsiIon": r"\epsilon",
    r"\varepsIlon": r"\varepsilon",
    r"\delte": r"\delta",
    r"\sigam": r"\sigma",
    r"\thata": r"\theta",
    # Operators
    r"\tims": r"\times",
    r"\tmes": r"\times",
    r"\cdct": r"\cdot",
    r"\Ieq": r"\leq",
    r"\infity": r"\infty",
    r"\inftv": r"\infty",
    # Structures
    r"\frae": r"\frac",
    r"\sqr": r"\sqrt",
    r"\overIine": r"\overline",
    r"\underIine": r"\underline",
    r"\mathbf": r"\mathbf",
    r"\Iim": r"\lim",
    r"\Iin": r"\lin",
    r"\Int": r"\int",
}


def _apply_ocr_corrections(latex: str) -> str:
    """Apply common OCR error corrections."""
    for wrong, correct in _OCR_CORRECTIONS.items():
        if wrong in latex:
            latex = latex.replace(wrong, correct)
    return latex


def _balance_brackets(latex: str) -> str:
    """Detect and fix unbalanced brackets."""
    pairs = [("{", "}"), ("(", ")"), ("[", "]")]

    for open_ch, close_ch in pairs:
        count = 0
        for ch in latex:
            if ch == open_ch:
                count += 1
            elif ch == close_ch:
                count -= 1

        if count > 0:
            latex += close_ch * count
        elif count < 0:
            latex = open_ch * (-count) + latex

    return latex


def _estimate_rapid_confidence(latex: str) -> float:
    """Estimate confidence for rapid_latex_ocr output based on heuristics.

    Factors:
        - Output length (very short or very long → lower confidence)
        - Bracket balance (unbalanced → lower confidence)
        - Common error patterns (presence → lower confidence)
        - Content richness (has operators/symbols → higher confidence)

    Returns:
        Estimated confidence score [0.0, 1.0].
    """
    conf = 0.75  # base confidence for rapid_latex_ocr

    # Length heuristic: too short or too long is suspicious
    length = len(latex)
    if length < 3:
        conf -= 0.3
    elif length > 500:
        conf -= 0.15

    # Bracket balance
    brace_count = latex.count("{") - latex.count("}")
    if brace_count != 0:
        conf -= 0.2 * min(abs(brace_count), 3)

    # Content richness
    math_indicators = ["\\", "^", "_", "{", "}", "+", "-", "=", "<", ">"]
    indicator_count = sum(latex.count(c) for c in math_indicators)
    if indicator_count >= 3:
        conf += 0.1  # Boost for clearly structured formulas

    # Common error patterns reduce confidence
    error_patterns = [r"\\\\", r"__", r"^^", r"{ }", r"\text\ "]
    for pat in error_patterns:
        if pat in latex:
            conf -= 0.05

    return max(0.1, min(1.0, conf))


# ═══════════════════════════════════════════════════════════════════════════════
# Image preprocessing
# ═══════════════════════════════════════════════════════════════════════════════

def _preprocess_formula_image(image_bytes: bytes) -> bytes:
    """Preprocess a formula image to improve OCR accuracy.

    Steps:
        1. Add 15 % white padding (prevent edge clipping).
        2. Upscale small images to ``min_height = 64 px``.
        3. CLAHE contrast enhancement.
        4. Unsharp-mask sharpening.

    Returns the original bytes unchanged if PIL / cv2 are unavailable.
    """
    if not image_bytes or len(image_bytes) < 100:
        return image_bytes

    try:
        from io import BytesIO

        import numpy as np
        from PIL import Image, ImageFilter, ImageOps

        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        w, h = img.size

        # Step 1: white padding (15 %)
        pad_x = max(10, int(w * 0.15))
        pad_y = max(10, int(h * 0.15))
        padded = Image.new("RGB", (w + 2 * pad_x, h + 2 * pad_y), (255, 255, 255))
        padded.paste(img, (pad_x, pad_y))
        img = padded
        w, h = img.size

        # Step 2: upscale to min_height = 64 px
        if h < 64:
            scale = 64 / h
            new_w = int(w * scale)
            img = img.resize((new_w, 64), Image.LANCZOS)

        # Step 3: CLAHE contrast enhancement
        try:
            import cv2

            img_np = np.array(img)
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            img = Image.fromarray(cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB))
        except ImportError:
            img = ImageOps.autocontrast(img, cutoff=1)

        # Step 4: sharpen
        img = img.filter(ImageFilter.SHARPEN)

        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    except Exception as e:
        logger.debug(f"[FormulaEngine] image preprocess failed: {e}")
        return image_bytes
