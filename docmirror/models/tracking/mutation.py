"""
Mutation 变换记录 (Data Lineage Tracker)
========================================

每一次Middleware对Data的操作都via Mutation 记录，
implement 100% 操作可追溯，满足金融级审计要求。

usingMode::

    mutation = Mutation.create(
        middleware_name="ColumnMapper",
        target_block_id="blk_a1",
        field_changed="column_name",
        old_value="交易日",
        new_value="transaction_date",
        confidence=0.95,
    )
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any, Optional


@dataclasses.dataclass
class Mutation:
    """
    单次Data变换记录。

    Attributes:
        middleware_name: Execute变换的MiddlewareName。
        target_block_id: 被变换的 Block ID。
        field_changed:   被变换的Field名。
        old_value:       变换前的值。
        new_value:       变换后的值。
        confidence:      变换的Confidence (0.0 ~ 1.0)。
        timestamp:       变换发生的时间。
        reason:          变换原因 (Optional，用于Debug)。
    """
    middleware_name: str
    target_block_id: str
    field_changed: str
    old_value: Any
    new_value: Any
    confidence: float = 1.0
    timestamp: datetime = dataclasses.field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    reason: str = ""

    @classmethod
    def create(
        cls,
        middleware_name: str,
        target_block_id: str,
        field_changed: str,
        old_value: Any,
        new_value: Any,
        confidence: float = 1.0,
        reason: str = "",
    ) -> Mutation:
        """FactoryMethod — 自动填充时间戳。"""
        return cls(
            middleware_name=middleware_name,
            target_block_id=target_block_id,
            field_changed=field_changed,
            old_value=old_value,
            new_value=new_value,
            confidence=confidence,
            reason=reason,
        )

    def to_dict(self) -> dict:
        """Serialization为 dict — 用于Log和持久化。"""
        return {
            "middleware": self.middleware_name,
            "block_id": self.target_block_id,
            "field": self.field_changed,
            "old": str(self.old_value)[:200],
            "new": str(self.new_value)[:200],
            "confidence": round(self.confidence, 4),
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
        }
