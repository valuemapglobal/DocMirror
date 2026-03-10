"""
Formula recognition engine (Formula Recognition Engine)
==========================================

Strategy patternEncapsulation的统一FormulaRecognizeEntry point。

优先级::

    UniMERNet ONNX (如Path有效) > rapid_latex_ocr > 空字符串

Usage::

    engine = FormulaEngine()
    latex = engine.recognize(image_bytes)

与 CoreExtractor 的关系:
    - CoreExtractor._recognize_formula() 委托给本Engine
    - 本Engine不Dependency CoreExtractor，可独立using/Test
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class FormulaEngine:
    """统一FormulaRecognizeEntry point — Strategy pattern。

    based on可用的后端自动选择最佳策略:
        1. UniMERNet ONNX (如果 model_path 指定且存在)
        2. rapid_latex_ocr (如果已安装)
        3. 空字符串 (无后端可用)

    all后端的Interface统一为: image_bytes → LaTeX string。
    """

    def __init__(self, model_path: Optional[str] = None):
        """InitializeFormulaEngine。

        Args:
            model_path: UniMERNet ONNX 模型Path。
                为 None 时Skip ONNX 后端，using rapid_latex_ocr Fallback。
        """
        self._model_path = model_path
        self._onnx_session = None
        self._rapid_ocr = None
        self._backend = "none"
        self._initialized = False

    def _lazy_init(self):
        """懒Initialize: 首次call recognize() 时Execute。"""
        if self._initialized:
            return
        self._initialized = True

        # 策略 1: UniMERNet ONNX
        if self._model_path:
            path = Path(self._model_path)
            if path.exists():
                try:
                    import onnxruntime as ort
                    self._onnx_session = ort.InferenceSession(
                        str(path),
                        providers=["CPUExecutionProvider"],
                    )
                    self._backend = "unimernet_onnx"
                    logger.info(f"[FormulaEngine] Using UniMERNet ONNX: {path}")
                    return
                except ImportError:
                    logger.debug("[FormulaEngine] onnxruntime not available")
                except Exception as e:
                    logger.warning(f"[FormulaEngine] ONNX load failed: {e}")

        # 策略 2: rapid_latex_ocr
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

        # 策略 3: 无后端
        self._backend = "none"
        logger.info("[FormulaEngine] No formula backend available")

    def recognize(self, image_bytes: bytes) -> str:
        """RecognizeFormulaImage为 LaTeX。

        Args:
            image_bytes: Formula区域的Image字节。

        Returns:
            LaTeX 字符串，RecognizeFailed时Returns空字符串。
        """
        if not image_bytes:
            return ""

        self._lazy_init()

        # P3-1: 图像预Processing (padding + resize + enhance)
        image_bytes = _preprocess_formula_image(image_bytes)

        try:
            if self._backend == "unimernet_onnx":
                return self._recognize_onnx(image_bytes)
            elif self._backend == "rapid_latex_ocr":
                return self._recognize_rapid(image_bytes)
        except Exception as e:
            logger.debug(f"[FormulaEngine] recognition error: {e}")

        return ""

    def _recognize_onnx(self, image_bytes: bytes) -> str:
        """UniMERNet ONNX Inference (预留Interface)。

        当前为 placeholder — 完整implementneed to UniMERNet 的
        Image预Processing + tokenizer Decoding逻辑。
        """
        # TODO: implement UniMERNet ONNX InferencePipeline
        # 1. image_bytes → PIL.Image → resize/normalize → numpy
        # 2. encoder forward → features
        # 3. decoder greedy/beam search → token ids
        # 4. tokenizer decode → LaTeX string
        logger.debug("[FormulaEngine] UniMERNet ONNX inference not yet implemented, falling back")

        # 临时Fallback到 rapid_latex_ocr (如果可用)
        if self._rapid_ocr is not None:
            return self._recognize_rapid(image_bytes)
        return ""

    def _recognize_rapid(self, image_bytes: bytes) -> str:
        """rapid_latex_ocr Inference。"""
        result, _ = self._rapid_ocr(image_bytes)
        return result or ""

    def recognize_and_normalize(self, image_bytes: bytes) -> str:
        """Recognize并Specification化 — 一步到位的便捷Interface。"""
        raw = self.recognize(image_bytes)
        if raw:
            return self.normalize_latex(raw)
        return ""

    @staticmethod
    def normalize_latex(latex: str) -> str:
        """LaTeX 深度Specification化 — 最大化 CDM Match率。

        操作 (按顺序):
            1. 去除首尾Whitespace和多余 $ 定界符
            2. OCR 常见Error correction
            3. 冗余命令Clean (\\displaystyle, \\textstyle 等)
            4. \\text{} / \\mathrm{} 内容Extract
            5. 括号平衡修正
            6. 冗余大括号简化
            7. WhitespaceSpecification化
        """
        if not latex or not latex.strip():
            return ""

        latex = latex.strip()

        # ── Step 1: 去除外 layer $ 定界符 ──
        if latex.startswith("$$") and latex.endswith("$$"):
            latex = latex[2:-2].strip()
        elif latex.startswith("$") and latex.endswith("$"):
            latex = latex[1:-1].strip()

        # 去除 \[ \] 定界符
        if latex.startswith("\\[") and latex.endswith("\\]"):
            latex = latex[2:-2].strip()

        # ── Step 2: OCR 常见Error correction ──
        latex = _apply_ocr_corrections(latex)

        # ── Step 3: 冗余命令Clean ──
        for cmd in (r"\displaystyle", r"\textstyle", r"\scriptstyle",
                    r"\scriptscriptstyle"):
            latex = latex.replace(cmd, "")

        # K4: \left. / \right. — 仅去除点号, retain \left/\right (CDM need to配对)
        latex = latex.replace(r"\left.", r"\left").replace(r"\right.", r"\right")

        # ── Step 4: \text{} / \mathrm{} / \mathit{} 内容Extract ──
        # \text{abc} → abc, \mathrm{d} → d
        latex = re.sub(
            r"\\(?:text|mathrm|mathit|mbox|hbox)\{([^{}]*)\}",
            r"\1", latex
        )

        # ── Step 5: 括号平衡修正 ──
        latex = _balance_brackets(latex)

        # ── Step 6: 冗余大括号简化 (保守Mode — CDM need to结构Information) ──
        # 仅简化独立的 {x} (前面not \ 命令Parameters位置)
        # 不再做广泛简化, CDM Calculate图ParseDependency括号结构

        # ── Step 7: WhitespaceSpecification化 ──
        latex = re.sub(r"\s+", " ", latex)
        # 操作符周围空格统一
        latex = re.sub(r"\s*([+\-=<>])\s*", r" \1 ", latex)
        # 逗号后加空格
        latex = re.sub(r",\s*", ", ", latex)
        latex = latex.strip()

        return latex

    @property
    def backend_name(self) -> str:
        """当前using的后端Name。"""
        self._lazy_init()
        return self._backend


# ═══════════════════════════════════════════════════════════════════════════════
# LaTeX Specification化Helper functions
# ═══════════════════════════════════════════════════════════════════════════════

# OCR 常见ErrorMapping table (rapid_latex_ocr 高频Error)
_OCR_CORRECTIONS = {
    # 希腊字母
    r"\Iambda": r"\lambda",
    r"\Gamma": r"\Gamma",  # 保持正确的不变
    r"\aIpha": r"\alpha",
    r"\bata": r"\beta",
    r"\epsiIon": r"\epsilon",
    r"\varepsIlon": r"\varepsilon",
    r"\delte": r"\delta",
    r"\sigam": r"\sigma",
    r"\thata": r"\theta",
    # 运算符
    r"\tims": r"\times",
    r"\tmes": r"\times",
    r"\cdct": r"\cdot",
    r"\Ieq": r"\leq",
    r"\geq": r"\geq",
    r"\neq": r"\neq",
    r"\infity": r"\infty",
    r"\inftv": r"\infty",
    # 结构
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
    """应用 OCR 常见Error correction。"""
    for wrong, correct in _OCR_CORRECTIONS.items():
        if wrong in latex:
            latex = latex.replace(wrong, correct)
    return latex


def _balance_brackets(latex: str) -> str:
    """Detect并Fix不平衡的括号。

    策略:
        - 统计各Type括号的开闭数量
        - 在末尾补齐缺失的闭括号
        - 在开头补齐缺失的开括号
    """
    pairs = [("{", "}"), ("(", ")"), ("[", "]")]

    for open_ch, close_ch in pairs:
        # 对 {} need to特殊Processing: ignore LaTeX 命令Internal的 {}
        count = 0
        for ch in latex:
            if ch == open_ch:
                count += 1
            elif ch == close_ch:
                count -= 1

        if count > 0:
            # 缺少闭括号
            latex += close_ch * count
        elif count < 0:
            # 缺少开括号 — 在开头补
            latex = open_ch * (-count) + latex

    return latex


def _preprocess_formula_image(image_bytes: bytes) -> bytes:
    """P3-1: Formula图像预Processing — 提升 OCR Recognize精度。

    rapid_latex_ocr 训练Data为Standard白底FormulaImage。
    直接Crop的 PDF 区域往往紧贴文字、对比度不足。

    Processing步骤:
        1. add 15% 白色 padding (prevent裁切过紧)
        2. 小图上采样到 min_height=64px
        3. CLAHE 对比度增强
        4. Unsharp Mask 锐化

    for PIL/cv2 不可用的Environment，直接Returns原始字节。
    """
    if not image_bytes or len(image_bytes) < 100:
        return image_bytes

    try:
        from io import BytesIO
        from PIL import Image, ImageFilter, ImageOps
        import numpy as np

        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        w, h = img.size

        # Step 1: add白色 padding (15%)
        pad_x = max(10, int(w * 0.15))
        pad_y = max(10, int(h * 0.15))
        padded = Image.new("RGB", (w + 2 * pad_x, h + 2 * pad_y), (255, 255, 255))
        padded.paste(img, (pad_x, pad_y))
        img = padded
        w, h = img.size

        # Step 2: 小图上采样 (min_height=64px)
        if h < 64:
            scale = 64 / h
            new_w = int(w * scale)
            img = img.resize((new_w, 64), Image.LANCZOS)

        # Step 3: CLAHE 对比度增强
        try:
            import cv2
            img_np = np.array(img)
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            # 转回 RGB
            img = Image.fromarray(cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB))
        except ImportError:
            # 无 cv2 时用 PIL 自动对比度
            img = ImageOps.autocontrast(img, cutoff=1)

        # Step 4: 锐化
        img = img.filter(ImageFilter.SHARPEN)

        # Output PNG
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    except Exception as e:
        logger.debug(f"[FormulaEngine] image preprocess failed: {e}")
        return image_bytes


