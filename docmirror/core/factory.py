"""
MultiModal Perception Factory
"""

from pathlib import Path
from typing import Union, Optional, TYPE_CHECKING
from docmirror.framework.dispatcher import ParserDispatcher
from docmirror.models.document_types import DocumentType

if TYPE_CHECKING:
    from docmirror.models.perception_result import PerceptionResult

class PerceptionFactory:
    """
    Perception factory that auto-dispatches parsing tasks by file type.
    ParserDispatcher is managed as a class-level cached singleton to avoid re-initialization.
    """
    _dispatcher: Optional[ParserDispatcher] = None

    @classmethod
    def get_dispatcher(cls) -> ParserDispatcher:
        if cls._dispatcher is None:
            cls._dispatcher = ParserDispatcher()
        return cls._dispatcher

    # backward-compat alias
    get_orchestrator = get_dispatcher

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        cls._dispatcher = None

import logging

logger = logging.getLogger(__name__)

# Convenience entry point
async def perceive_document(
    file_path: Union[str, Path],
    document_type: DocumentType = DocumentType.OTHER
) -> "PerceptionResult":
    logger.info(f"[PerceptionFactory] ▶ perceive_document | file_path={file_path} | document_type={document_type}")
    dispatcher = PerceptionFactory.get_dispatcher()
    return await dispatcher.process(str(file_path), document_type=document_type)
