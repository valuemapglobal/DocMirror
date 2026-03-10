"""
MultiModal Exception体系 (Exception Hierarchy)
======================================

统一的Type化Exception layer级，替代裸 Exception。

层级结构::

    MultiModalError (base)
    ├── ExtractionError      — CoreExtractor / 物理Extraction failed
    ├── LayoutAnalysisError   — 版面Analyze / Zone PartitionedFailed
    ├── MiddlewareError       — MiddlewareProcessingFailed (携带 middleware_name)
    └── ValidationError       — DataVerify不via

using指南:
    - 可resumeError: 在 try/except 中捕获并 add_error(), 不终止Pipeline
    - 不可resumeError: 抛出，由上 layer Pipeline 的 fail_strategy 决定Processing方式
"""

from __future__ import annotations


class MultiModalError(Exception):
    """MultiModal ExceptionBase class。"""

    def __init__(self, message: str = "", *, detail: str = ""):
        self.detail = detail
        super().__init__(message)


class ExtractionError(MultiModalError):
    """CoreExtractor 物理Extract过程中的Error。

    示例: PDF 打开Failed, pdfplumber ParseFailed, Page超上限等。
    """
    pass


class LayoutAnalysisError(MultiModalError):
    """版面Analyze / Zone Partitioned / TableExtract layer的Error。"""
    pass


class MiddlewareError(MultiModalError):
    """MiddlewareProcessing过程中的Error。

    Attributes:
        middleware_name: 出错的MiddlewareName。
    """

    def __init__(self, message: str = "", *, middleware_name: str = "", detail: str = ""):
        self.middleware_name = middleware_name
        super().__init__(message, detail=detail)

    def __str__(self):
        prefix = f"[{self.middleware_name}] " if self.middleware_name else ""
        return f"{prefix}{super().__str__()}"


class ValidationError(MultiModalError):
    """DataVerify不via。

    示例: TableInconsistent column count, Dateoverride率过低, Confidence低于Threshold等。
    """
    pass
