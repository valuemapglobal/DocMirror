"""RapidTable SingletonEngine — Thread-safe的Table结构Recognize。

Usage::

    from .rapid_table_engine import get_rapid_table_engine
    engine = get_rapid_table_engine()
    result = engine(img_np)  # -> RapidTableOutput
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from rapid_table import RapidTable, RapidTableInput, RapidTableOutput
    HAS_RAPID_TABLE = True
except ImportError:
    HAS_RAPID_TABLE = False


class RapidTableEngine:
    """Thread-safe的 RapidTable Singleton。

    首次call时懒Load模型 (~1-3s), 后续call复用同一Instance。
    """

    _instance: Optional["RapidTableEngine"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._engine = None
        self._available = HAS_RAPID_TABLE

    @classmethod
    def get_instance(cls) -> "RapidTableEngine":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _ensure_engine(self) -> bool:
        """懒LoadEngine, ReturnsWhether可用。"""
        if not self._available:
            return False
        if self._engine is not None:
            return True
        with self._lock:
            if self._engine is not None:
                return True
            try:
                logger.info("[RapidTable] Initializing model...")
                self._engine = RapidTable()
                logger.info("[RapidTable] Model loaded.")
                return True
            except Exception as e:
                logger.warning(f"[RapidTable] Init failed: {e}")
                self._available = False
                return False

    def __call__(self, img) -> Optional["RapidTableOutput"]:
        """运行Table结构Recognize。

        Args:
            img: numpy ndarray (RGB/BGR), PIL Image, 或ImagePath。

        Returns:
            RapidTableOutput 或 None (不可用/Failed时)。
        """
        if not self._ensure_engine():
            return None
        try:
            return self._engine(img)
        except Exception as e:
            logger.debug(f"[RapidTable] Inference error: {e}")
            return None

    @property
    def is_available(self) -> bool:
        return self._available


def get_rapid_table_engine() -> RapidTableEngine:
    """获取Global RapidTable EngineSingleton。"""
    return RapidTableEngine.get_instance()
