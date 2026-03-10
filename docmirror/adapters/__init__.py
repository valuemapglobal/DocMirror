"""
Adapters — Format adapter layer
========================

each Adapter 负责:
    1. 将特定FormatFileConvert为 ``BaseResult``
    2. Optional地直接Returns ``ParserOutput`` (Backward compatible)

Adapter 不引入any业务逻辑 — 业务增强由 Middleware Pipeline统一Processing。
"""

from .pdf import PDFAdapter
from .image import ImageAdapter
from .email import EmailAdapter
from .excel import ExcelAdapter
from .word import WordAdapter
from .ppt import PPTAdapter
from .structured import StructuredAdapter
from .web import WebAdapter

__all__ = [
    "PDFAdapter",
    "ImageAdapter",
    "EmailAdapter",
    "ExcelAdapter",
    "WordAdapter",
    "PPTAdapter",
    "StructuredAdapter",
    "WebAdapter",
]
