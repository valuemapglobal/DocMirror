
"""
多模态ParseDispatcher (MultiModal Parser Dispatcher)

This module is the L0 routing layer of the document parsing system.
它的设计哲学是“单一职责”：
1. L0: File type detection → dispatch to corresponding parser.
2. L1 & L2: PDF internal business category and institution identification is delegated to DigitalPDFParser.

Architecture model:
    - Dispatcher (L0): File format routing (PDF, Image, Office...)
    - DigitalPDFParser (L1/L2): PDF deep classification & routing (bank statement, credit report...)
    - InstitutionPlugin: Institution-specific parsing logic
"""

import logging
import filetype
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, Type, Optional, Union, Any, List

from docmirror.framework.base import BaseParser, ParserOutput, ParserStatus

# Initialize logger
logger = logging.getLogger(__name__)


class ParserDispatcher:
    """
    ParserDispatcher is the entry point for the parsing pipeline.
    
    Responsibilities:
    - I/O-level file validation (existence, size).
    - Fast file type identification (Magic Number + Extension).
    - Select optimal parser by file type.
    - Handle fallback strategy after primary parse failure.
    """

    async def process(
        self, 
        file_path: Union[str, Path], 
        fallback: bool = True,
        document_type=None,
        skip_cache: bool = False,
        **kwargs
    ) -> Any:
        """
        Main entry point for document parsing.

        Calls adapter.perceive() to directly return PerceptionResult (new path).
        """
        _t0 = time.time()
        path = Path(file_path)

        # ── 1. File context preparation ──
        import hashlib
        _file_checksum = ""
        _file_mime = ""
        file_size = 0
        if path.exists():
            try:
                _file_bytes = path.read_bytes()
                file_size = len(_file_bytes)
                _file_checksum = hashlib.sha256(_file_bytes).hexdigest()
                del _file_bytes
            except OSError:
                pass
            _ft = filetype.guess(str(path))
            _file_mime = _ft.mime if _ft else ""

        # ── 2. Cache lookup ──
        if not skip_cache and _file_checksum:
            from docmirror.framework.cache import parse_cache
            try:
                cached_json = await parse_cache.get(_file_checksum, document_type or "")
                if cached_json:
                    from docmirror.models.perception_result import PerceptionResult
                    logger.info(f"[Dispatcher] ⚡ Cache HIT for {path.name}")
                    return PerceptionResult.model_validate_json(cached_json)
            except Exception as e:
                logger.debug(f"[Dispatcher] Cache lookup error (non-fatal): {e}")

        # ── 3. Physical validation ──
        _file_type = ""
        _is_forged: Optional[bool] = None
        _forgery_reasons: List[str] = []

        if not path.exists():
            return self._build_failure(f"File not found: {file_path}", _t0, str(path))

        _MAX_FILE_SIZE = 200 * 1024 * 1024
        if file_size > _MAX_FILE_SIZE:
            return self._build_failure(f"File too large: {file_size / 1024 / 1024:.1f}MB (max 200MB)", _t0, str(path))
        if file_size == 0:
            return self._build_failure("File is empty (0 bytes)", _t0, str(path))

        # ── 4. L0 routing ──
        file_type = self._detect_file_type(path)
        _file_type = file_type
        logger.info(f"[Dispatcher] ▶ process | file={path.name} | size={file_size}B | fallback={fallback} | doc_type={document_type}")
        logger.info(f"[Dispatcher] L0 detected file_type={file_type}")

        if document_type:
            kwargs["document_type"] = document_type

        parser = self._get_parser_for_type(file_type)
        if not parser:
            return self._build_failure(f"Unsupported format: {file_type}", _t0, str(path), file_type=_file_type)

        # ── 5. Forgery detection ──
        try:
            if file_type == 'pdf':
                from docmirror.core.security.forgery_detector import detect_pdf_forgery
                _is_forged, _forgery_reasons = detect_pdf_forgery(path)
            elif file_type == 'image':
                from docmirror.core.security.forgery_detector import detect_image_forgery
                _is_forged, _forgery_reasons = detect_image_forgery(path)
        except Exception as e:
            logger.warning(f"Forgery Detection Engine error: {e}")

        # ── 6. Parse dispatch — call perceive() to return PerceptionResult ──
        pname = parser.__class__.__name__
        # Build context for perceive/Builder
        context = {
            "file_path": str(path),
            "file_type": _file_type,
            "file_size": file_size,
            "parser_name": pname,
            "started_at": datetime.fromtimestamp(_t0),
            "mime_type": _file_mime,
            "checksum": _file_checksum,
            "is_forged": _is_forged,
            "forgery_reasons": _forgery_reasons,
        }
        try:
            logger.info(f"Dispatching to {pname}")
            # The first positional arg of perceive() is file_path,
            # to avoid "got multiple values for argument 'file_path'" error,
            # remove file_path before spreading **context.
            perceive_ctx = {k: v for k, v in context.items() if k != "file_path"}
            perception = await parser.perceive(path, **perceive_ctx)

            # ── 7. Fallback error handling ──
            if fallback and (not perception.success or not perception.content.text.strip()):
                fallback_parser = self._get_fallback_parser(file_type)
                if fallback_parser and fallback_parser.__class__ != parser.__class__:
                    logger.info(f"Primary {pname} failed/empty, attempting fallback: {fallback_parser.__class__.__name__}")
                    context["parser_name"] = fallback_parser.__class__.__name__
                    fb_ctx = {k: v for k, v in context.items() if k != "file_path"}
                    fb_perception = await fallback_parser.perceive(path, **fb_ctx)
                    if fb_perception.success and fb_perception.content.text.strip():
                        _elapsed = int((time.time() - _t0) * 1000)
                        fb_perception.timing.elapsed_ms = _elapsed
                        logger.info(f"[Dispatcher] ◀ process | parser={fallback_parser.__class__.__name__}(fallback) | status={fb_perception.status} | elapsed={_elapsed}ms")
                        return fb_perception

            # ── 8. Timing + logging ──
            _elapsed = int((time.time() - _t0) * 1000)
            perception.timing.elapsed_ms = _elapsed
            logger.info(f"[Dispatcher] ◀ process | parser={pname} | status={perception.status} | confidence={perception.confidence:.4f} | text_len={len(perception.content.text)} | tables={len(perception.tables)} | forged={_is_forged} | elapsed={_elapsed}ms")

            # ── 9. Write cache (success only) ──
            if _file_checksum and perception.success:
                try:
                    from docmirror.framework.cache import parse_cache
                    await parse_cache.set(
                        _file_checksum, document_type or "",
                        perception.model_dump_json(),
                    )
                except Exception as e:
                    logger.debug(f"[Dispatcher] Cache write error (non-fatal): {e}")

            return perception

        except Exception as e:
            logger.error(f"Critical orchestration error: {e}", exc_info=True)
            return self._build_failure(f"Orchestration failure: {str(e)}", _t0, str(path),
                                       file_type=_file_type, is_forged=_is_forged, forgery_reasons=_forgery_reasons)

    @staticmethod
    def _build_failure(
        error_msg: str,
        t0: float,
        file_path: str = "",
        file_type: str = "",
        is_forged: Optional[bool] = None,
        forgery_reasons: Optional[List[str]] = None,
    ):
        """Build a failure PerceptionResult (replaces legacy _wrap(ParserOutput(FAILURE)))."""
        from docmirror.models.perception_result import (
            PerceptionResult, ResultStatus, ErrorDetail, TimingInfo, Provenance, SourceInfo,
            DocumentContent, ValidationResult,
        )
        elapsed = (time.time() - t0) * 1000
        validation = None
        if is_forged is not None:
            validation = ValidationResult(is_forged=is_forged, forgery_reasons=forgery_reasons or [])
        return PerceptionResult(
            status=ResultStatus.FAILURE,
            confidence=0.0,
            timing=TimingInfo(elapsed_ms=elapsed),
            error=ErrorDetail(message=error_msg),
            content=DocumentContent(),
            provenance=Provenance(
                source=SourceInfo(file_path=file_path, file_type=file_type),
                validation=validation,
            ),
        )

    def _detect_file_type(self, path: Path) -> str:
        """
        Uses Magic Number (filetype) combined with extension for composite detection.
        
        Why not just extension? Extensions can be tampered with and are unreliable.
        Why not just Magic Number? Some Office formats (DOC) have ambiguous magic numbers.
        """
        try:
            kind = filetype.guess(str(path))
            if kind:
                mime = kind.mime
                if mime == 'application/pdf':
                    return 'pdf'
                if mime.startswith('image/'):
                    return 'image'
        except:
            pass

        ext = path.suffix.lower()
        mapping = {
            '.pdf': 'pdf',
            '.doc': 'word', '.docx': 'word',
            '.xls': 'excel', '.xlsx': 'excel',
            '.ppt': 'ppt', '.pptx': 'ppt',
            '.png': 'image', '.jpg': 'image', '.jpeg': 'image', '.tiff': 'image', '.bmp': 'image',
            '.json': 'structured', '.xml': 'structured', '.csv': 'structured',
            '.eml': 'email', '.msg': 'email',
            '.html': 'web', '.htm': 'web'
        }
        return mapping.get(ext, 'unknown')

    def _get_parser_for_type(self, file_type: str) -> Optional[BaseParser]:
        """
        L0 static mapping table — Adapter layer preferred.
        PDF using统一的 MultiModalParser (via PDFAdapter Routing)。
        """
        if file_type == 'pdf':
            import os
            from docmirror.adapters.pdf import PDFAdapter
            logger.info("[Dispatcher] Using PDFAdapter (promoted)")
            return PDFAdapter(enhance_mode=os.environ.get("DOCMIRROR_ENHANCE_MODE", "standard"))
        elif file_type == 'image':
            from docmirror.adapters.image import ImageAdapter
            return ImageAdapter()
        elif file_type == 'word':
            from docmirror.adapters.word import WordAdapter
            return WordAdapter()
        elif file_type == 'excel':
            from docmirror.adapters.excel import ExcelAdapter
            return ExcelAdapter()
        elif file_type == 'ppt':
            from docmirror.adapters.ppt import PPTAdapter
            return PPTAdapter()
        elif file_type == 'email':
            from docmirror.adapters.email import EmailAdapter
            return EmailAdapter()
        elif file_type == 'structured':
            from docmirror.adapters.structured import StructuredAdapter
            return StructuredAdapter()
        elif file_type == 'web':
            from docmirror.adapters.web import WebAdapter
            return WebAdapter()
        return None

    def _get_fallback_parser(self, file_type: str) -> Optional[BaseParser]:
        """
        Defines fallback strategy when primary parser fails.
        
        当前 PDF 没有更底 layer的Downgrade parser，如果 MultiModal Failed，直接Returns None。
        """
        if file_type == 'pdf':
            # MultiModal 集成了all手段(含 OCR) ，不再向Scanned document老代码Downgrade。
            return None
        return None
