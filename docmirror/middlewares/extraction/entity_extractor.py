"""
Entity extraction middleware (Entity Extractor Middleware)
=============================================

从 extractor.py 的 _extract_entities_from_text() 抽离的业务逻辑 layer。
负责从Document全文和已Extract的 KV blocks 中Recognize银行名、Account name、Account number、Period等关键实体。

Design principles:
    - Configuration驱动: 实体正则Mode未来可via hints.yaml Extension
    - 职责分离: CoreExtractor 只做物理Extract, Entity recognitionbelongs to业务增强
    - 可插拔: 作为StandardMiddleware, 可在any enhance_mode 下自由装卸
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from ..base import BaseMiddleware
from ...models.enhanced import EnhancedResult

logger = logging.getLogger(__name__)

# Field标签Filter (avoid把Field名误Recognize为Account name)
_FIELD_LABELS = re.compile(
    r'客户号|Account number|账单|Currency|标志|Type|Date|Amount|Balance|合计|页数|凭证|编号|条件|证件|Abstract/Summary|流水|交易|期末|期初|汇总'
)


class EntityExtractor(BaseMiddleware):
    """
    Entity extraction middleware — RecognizeDocument中的关键业务实体。

    从Document全文和已Extract的 key_value blocks 中Recognize:
      - 银行名 (bank_name)
      - Account name
      - Account number
      - Query period
      - Print date
      - Currency
    """

    def process(self, result: EnhancedResult) -> EnhancedResult:
        """Execute实体Extract。"""
        base = result.base_result
        full_text = base.full_text or ""
        pages = base.pages

        entities: Dict[str, str] = {}

        # 1. 从已Extract的 key_value blocks 收集
        for page in pages:
            for block in page.blocks:
                if block.block_type == "key_value" and isinstance(block.raw_content, dict):
                    entities.update(block.raw_content)

        # 2. 正则兜底: 从首页文本Extract
        first_page_text = full_text[:500] if full_text else ""

        self._extract_bank_name(entities, first_page_text)
        self._extract_account_holder(entities, first_page_text, pages)
        self._extract_account_number(entities, first_page_text, pages)
        self._extract_period(entities, first_page_text)
        self._extract_print_date(entities, first_page_text)
        self._extract_currency(entities, first_page_text)

        # 写入 enhanced_data
        result.enhanced_data["extracted_entities"] = entities
        logger.info(f"[DocMirror] EntityExtractor: {list(entities.keys())}")

        return result

    def _extract_bank_name(self, entities: Dict, text: str) -> None:
        if "bank_name" in entities or "Bank name" in entities:
            return
        bank_patterns = [
            r'(中国[建工农交]设?银行)',
            r'(招商银行|兴业银行|浦发银行|民生银行|中信银行|光大银行|华夏银行|平安银行)',
            r'(中[国]?银行)',
            r'([\u4e00-\u9fa5]{2,8}银行)',
        ]
        for pat in bank_patterns:
            m = re.search(pat, text)
            if m:
                entities["bank_name"] = m.group(1)
                break

    def _extract_account_holder(self, entities: Dict, text: str, pages) -> None:
        if any(k in entities for k in ("Account name", "Account name", "Customer name", "Customer name")):
            return
        for pat in [
            r'(?:本方)?Account name[：:]\s*(.+?)(?:\n|$)',
            r'(?:Account name称|Customer name|Customer name|Account holder|Card holder)[：:]\s*(.+?)(?:\n|$)',
            r'(?:Account name称|Customer name|Customer name)\n(.+?)(?:\n|$)',
            r'戶名[：:]?\s*(.+?)(?:\n|$)',
            r'Account\s*Name[：:]?\s*(.+?)(?:\n|$)',
        ]:
            m = re.search(pat, text)
            if m:
                val = m.group(1).strip()
                if (val and 2 <= len(val) <= 30
                        and not val.isdigit()
                        and not re.match(r'^\d{4}[-/]\d{2}[-/]\d{2}', val)
                        and not _FIELD_LABELS.match(val)):
                    entities["Account name"] = val
                    return

        # Table回溯
        _name_keywords = ["Account name", "Account name", "Customer name", "Customer name", "Account name称", "Account holder"]
        for page in pages:
            for block in page.blocks:
                if block.block_type == "table" and isinstance(block.raw_content, list):
                    tbl_headers = block.raw_content[0] if block.raw_content else []
                    for i, h in enumerate(tbl_headers):
                        if h and any(kw in str(h) for kw in _name_keywords):
                            if len(block.raw_content) > 1 and i < len(block.raw_content[1]):
                                val = str(block.raw_content[1][i]).strip()
                                if (val and 2 <= len(val) <= 30
                                        and not val.isdigit()
                                        and not re.match(r'^\d{4}[-/]\d{2}[-/]\d{2}', val)):
                                    entities["Account name"] = val
                                    return

    def _extract_account_number(self, entities: Dict, text: str, pages) -> None:
        if "Account number" in entities:
            return
        for pat in [
            r'账\s*号[：:]\s*(\d{10,25})',
            r'卡\s*号[：:]\s*(\d{10,25})',
            r'Account\s*(?:No\.?|Number)[：:]?\s*(\d{10,25})',
            r'账戶[：:]?\s*(\d{10,25})',
        ]:
            m = re.search(pat, text)
            if m:
                entities["Account number"] = m.group(1).strip()
                return
        # Table回溯
        for page in pages:
            for block in page.blocks:
                if block.block_type == "table" and isinstance(block.raw_content, list):
                    headers = block.raw_content[0] if block.raw_content else []
                    for i, h in enumerate(headers):
                        if h and "Account number" in str(h):
                            if len(block.raw_content) > 1:
                                val = str(block.raw_content[1][i]).strip()
                                if val and len(val) >= 10:
                                    entities["Account number"] = val
                                    return
                    break

    def _extract_period(self, entities: Dict, text: str) -> None:
        if "Query period" in entities or "Period" in entities:
            return
        for pat in [
            r'(?:Query|交易|账单)Period[：:]\s*(.+?)(?:\n|$)',
            r'(\d{4}年\d{1,2}月\d{1,2}日?\s*[-至到]\s*\d{4}年\d{1,2}月\d{1,2}日?)',
        ]:
            m = re.search(pat, text)
            if m:
                entities["Query period"] = m.group(1).strip()
                return

    def _extract_print_date(self, entities: Dict, text: str) -> None:
        if "Print date" in entities:
            return
        m = re.search(r'Print date[：:]\s*(\d{4}年\d{1,2}月\d{1,2}日)', text)
        if m:
            entities["Print date"] = m.group(1).strip()

    def _extract_currency(self, entities: Dict, text: str) -> None:
        if "Currency" in entities:
            return
        if "人民币" in text:
            entities["Currency"] = "CNY"
