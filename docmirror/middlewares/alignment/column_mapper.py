"""
Column mapping middleware (Column Mapper)
==============================

三 layer递进式列Map:
    Tier 1 (精确Match): hints.yaml 中的Standard名 + 别名
    Tier 2 (Fuzzy matching): 编辑距离 + 子串contains + 同义词
    Tier 3 (LLM N选M): 仅对未Match列Request LLM

从 v1 的 processor.py 移植核心Map逻辑和 TARGET_COLUMNS define。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ..base import BaseMiddleware
from ...models.enhanced import EnhancedResult

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Standard化目标列 — 从 YAML Load (fallback 到硬Encoding)
# ═══════════════════════════════════════════════════════════════════════════════

def _load_column_config() -> dict:
    """从 column_aliases.yaml Load列MapConfiguration。"""
    import yaml
    from pathlib import Path
    config_path = Path(__file__).parent.parent.parent / "configs" / "column_aliases.yaml"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.warning(f"[ColumnMapper] Failed to load column_aliases.yaml: {e}, using defaults")
        return {}

_COL_CONFIG = _load_column_config()

TARGET_COLUMNS = _COL_CONFIG.get("target_columns", [
    "序号", "交易时间", "对方Account number与Account name", "Abstract/Summary", "用途", "备注",
    "Transaction amount", "AccountBalance", "钞汇", "币别",
])

SKIP_COLUMNS = set(_COL_CONFIG.get("skip_columns", [
    "企业流水号", "凭证种类", "凭证号", "交易介质编号",
    "Account明细编号-交易流水号", "凭证Type凭证号码", "凭证Type 凭证号码",
    "凭证Type", "凭证号码", "交易渠道", "交易机构", "对方行名",
    "借贷Status", "支/收", "借贷标志", "收支", "柜员流水号", "Abstract/Summary代码",
]))

COLUMN_ALIASES: Dict[str, List[str]] = _COL_CONFIG.get("column_aliases", {
    "序号": ["流水号", "序", "编号", "Seq", "No", "SeqNo", "序号"],
    "交易时间": ["Transaction date", "Date", "交易日", "记账Date", "入账Date", "Date", "Transaction Date", "记帐Date", "交易时间"],
    "对方Account number与Account name": ["对方Account name", "对方Name", "收/付款人", "对方Account", "Counterparty", "对手方", "对方Information", "交易对手Information", "交易对手", "对方Account name/Account number", "对方Account/对方银行", "交易机构对方Account name/Account number"],
    "Abstract/Summary": ["交易Abstract/Summary", "Abstract/Summary", "说明", "用途/Abstract/Summary", "备注/Abstract/Summary", "Description", "Summary", "交易Type", "业务Abstract/Summary", "交易方式", "序号Abstract/Summary", "序号 Abstract/Summary"],
    "用途": ["用途", "附言", "Purpose", "Remark", "交易地点/附言", "交易地点"],
    "备注": ["备注", "Memo", "Note", "附注"],
    "Transaction amount": ["Amount", "Transaction amount", "Transaction amount", "Amount", "收入Amount", "支出Amount", "人民币", "交易额", "收入", "支出"],
    "AccountBalance": ["Balance", "AccountBalance", "Balance", "结存", "可用Balance", "期末Balance", "本次Balance", "AccountBalance现转标志交易渠道", "AccountBalance 现转标志 交易渠道"],
    "钞汇": ["钞汇标志", "钞汇", "Cash/Transfer", "币别钞汇", "币别 钞汇", "现转标志", "现转"],
    "币别": ["Currency", "币别", "Currency", "CCY"],
})

# 借贷分列关键字 (不参与普通列Map，由 split amount 逻辑Processing)
INCOME_KEYWORDS = set(_COL_CONFIG.get("income_keywords", ["收入", "Credit", "存入", "收入Amount", "CreditTransaction amount", "Credit"]))
EXPENSE_KEYWORDS = set(_COL_CONFIG.get("expense_keywords", ["支出", "Debit", "支取", "支出Amount", "DebitTransaction amount", "Debit"]))
# Transaction amount类关键字 (用于Detect空Table header邻接列分列Mode)
AMOUNT_LIKE_KEYWORDS = set(_COL_CONFIG.get("amount_like_keywords", ["Transaction amount", "Amount", "Transaction amount", "交易额", "Amount"]))


# ═══════════════════════════════════════════════════════════════════════════════
# Header-Data Alignment & Amount Split (已Extract为独立Module)
# ═══════════════════════════════════════════════════════════════════════════════
from .header_alignment import infer_column_type, verify_header_data_alignment
from .amount_splitter import detect_split_amount as _detect_split_amount_fn

# Table header名 → 期望的Data列Type (供 header_alignment using)
_HEADER_TYPE_EXPECTATIONS: Dict[str, str] = {
    "交易时间": "date", "Transaction date": "date", "Date": "date",
    "记账Date": "date", "入账Date": "date", "交易日": "date", "Date": "date",
    "Transaction amount": "amount", "Amount": "amount", "Transaction amount": "amount", "Amount": "amount",
    "AccountBalance": "amount", "Balance": "amount", "结存": "amount", "Balance": "amount",
    "序号": "seq", "流水号": "seq",
}
for _std_name, _aliases in COLUMN_ALIASES.items():
    if _std_name in _HEADER_TYPE_EXPECTATIONS:
        _expected_type = _HEADER_TYPE_EXPECTATIONS[_std_name]
        for _alias in _aliases:
            if _alias not in _HEADER_TYPE_EXPECTATIONS:
                _HEADER_TYPE_EXPECTATIONS[_alias] = _expected_type


class ColumnMapper(BaseMiddleware):
    """
    Column mapping middleware。

    将从 BaseResult Extract的原始Table headerMap到Standard column name。
    Output ``EnhancedResult.enhanced_data["standardized_tables"]`` — 多 table结构。
    """

    def process(self, result: EnhancedResult) -> EnhancedResult:
        """Execute列Map并生成Standard化Table (supports多 table)。"""
        if result.base_result is None:
            return result

        # 仅对 bank_statement 场景Execute完整Map
        if result.scene not in ("bank_statement", "unknown"):
            logger.info(f"[ColumnMapper] scene={result.scene}, skipping bank_statement mapping")
            return result

        # 按机构Merge hints 中的列别名（含 scene column_map）
        effective_aliases = self._effective_column_aliases(result)

        # 获取allTable块
        table_blocks = result.base_result.table_blocks
        if not table_blocks:
            logger.info("[ColumnMapper] No table blocks found")
            return result

        # ── 多页TableMerge: 按顺序分组 ──
        groups = self._merge_table_blocks(table_blocks)
        if not groups:
            return result

        # ── 为each table组生成Standard化Result ──
        standardized_tables = []

        for idx, group in enumerate(groups):
            raw_headers = group["header"]
            data_rows = group["rows"]

            if not data_rows:
                continue

            # ── Table header-Data列AlignmentVerify ──
            raw_headers = self._verify_header_data_alignment(
                raw_headers, data_rows, result,
            )
            group["header"] = raw_headers  # 回写，供后续using

            # Execute三 layerMap（传入按机构Merge后的别名）
            mapping, unmapped = self._map_columns(raw_headers, effective_aliases)

            # Detect收入/支出分列 (F-6: 传入Data行用于Validate)
            has_split_amount, split_income_idx, split_expense_idx = (
                self._detect_split_amount(raw_headers, mapping, data_rows)
            )

            # 生成Standard化Table
            block_id = group["block"].block_id if group["block"] else f"table_{idx}"
            std_table = self._standardize(
                raw_headers, data_rows, mapping,
                has_split_amount=has_split_amount,
                split_income_idx=split_income_idx,
                split_expense_idx=split_expense_idx,
                block_id=block_id,
                result=result,
            )

            mapped_count = sum(1 for v in mapping.values() if v is not None)

            table_entry = {
                "table_id": f"table_{idx}",
                "headers": std_table[0] if std_table else [],
                "rows": std_table[1:] if std_table else [],
                "row_count": len(std_table) - 1 if std_table else 0,
                "column_mapping": mapping,
                "unmapped_columns": unmapped,
                "has_split_amount": has_split_amount,
                "source_block_id": block_id,
            }
            standardized_tables.append(table_entry)

            logger.info(
                f"[ColumnMapper] table_{idx}: mapped {mapped_count}/{len(raw_headers)} "
                f"columns | rows={table_entry['row_count']} | unmapped={unmapped}"
            )

        result.enhanced_data["standardized_tables"] = standardized_tables

        # Backward compatible: standardized_table = 最大 table的完整二维数组
        if standardized_tables:
            main = max(standardized_tables, key=lambda t: t["row_count"])
            result.enhanced_data["standardized_table"] = (
                [main["headers"]] + main["rows"]
            )
            result.enhanced_data["standardized_headers"] = main["headers"]
            result.enhanced_data["column_mapping"] = main["column_mapping"]
            result.enhanced_data["unmapped_columns"] = main["unmapped_columns"]
            result.enhanced_data["raw_headers"] = main["headers"]
            result.enhanced_data["has_split_amount"] = main["has_split_amount"]

        return result

    # Table header质量Detect正则 (含Date或Amount → may是Data行误做Table header)
    _RE_HEADER_IS_DATA = re.compile(
        r'\d{4}[/-]\d{2}[/-]\d{2}'   # Date
        r'|^\d[\d,]*\.\d{2}$'        # Amount
        r'|^\d{10,}$'                # 长数字串 (Account number)
        r'|[：:].{3,}'               # KV Format (如 "Account number:621460...")
        r'|银行.{0,4}(交易|流水|明细|对账)'  # Title文字
        r'|\d{6}\*{2,}'              # 掩码Account number (如 621460****)
    )

    def _effective_column_aliases(self, result: EnhancedResult) -> Dict[str, List[str]]:
        """
        Merge通用 column_aliases 与机构维度的 scene column_map。
        当 result.enhanced_data["institution"] 存在时，从 hints.scenes 中取
        {institution}_bank_statement 的 column_map，将 raw_header -> standard_name 转为别名List。
        """
        aliases = dict(self.config.get("column_aliases", {}))
        # 深拷贝一 layer，avoid修改 config
        for k, v in list(aliases.items()):
            if isinstance(v, list):
                aliases[k] = list(v)
            else:
                aliases[k] = [v] if isinstance(v, str) else []

        inst = result.enhanced_data.get("institution")
        hints = self.config.get("hints") or {}
        scenes = hints.get("scenes") or []
        if inst and scenes:
            scene_name = f"{inst}_bank_statement"
            for s in scenes:
                if s.get("name") == scene_name:
                    column_map = s.get("column_map") or {}
                    for raw_name, spec in column_map.items():
                        if isinstance(spec, dict):
                            std = spec.get("standard_name")
                        else:
                            std = None
                        if std and raw_name:
                            aliases.setdefault(std, []).append(raw_name)
                    logger.debug(f"[ColumnMapper] merged aliases from scene={scene_name}")
                    break
        return aliases

    def _merge_table_blocks(self, table_blocks):
        """
        按顺序Merge多个 table block (多页续 table) — **Middleware级分组**。

        与 ``core.table_merger.merge_cross_page_tables`` (Step 4) 互补:
          - **table_merger** (Step 4): Extract阶段Merge跨页 Block 的 raw_content
          - **本Method** (Step 7): 列Map阶段做逻辑分组 (header + data rows),
            supports弹性Merge、多 table分离

        算法 (Sequential Grouping):
            1. 按块顺序遍历
            2. 判断each块的首行是 Table header or Data行 (首列含Date → Data行)
            3. 首行是Table header → 检查Whether与当前组Table headerMatch:
               - Match → Skip重复Table header, Data行加入当前组
               - 不Match → Enable新组
            4. 首行是Data行 (续页) → all行加入当前组
            5. Returns最大的组
        """
        import re
        _date_re = re.compile(r'^\d{4}[-/]?\d{2}[-/]?\d{2}')

        # Filter有效Table
        valid = [
            b for b in table_blocks
            if isinstance(b.raw_content, list) and len(b.raw_content) >= 2
        ]
        if not valid:
            valid = [
                b for b in table_blocks
                if isinstance(b.raw_content, list) and len(b.raw_content) >= 1
            ]
            if not valid:
                return None, None
            return valid[0].raw_content, valid[0]

        def _is_data_row(row):
            """判断行Whether是Data行 (首列含Date)。"""
            return row and _date_re.match(str(row[0]).strip())

        def _headers_match(h1, h2):
            """
            判断两个Table headerWhetherbelongs to同一张 table。

            算法: 拼接字符串Compare — 消除列边界差异 (粘连不可拆)。
            例: ['序号Abstract/Summary', '币别钞汇'] vs ['序号', 'Abstract/Summary', '币别', '钞汇']
              → "序号Abstract/Summary币别钞汇" == "序号Abstract/Summary币别钞汇" → 同一张 table
            """
            if not h1 or not h2:
                return False
            # 去空格拼接: 消除列边界差异
            s1 = "".join(str(c).strip() for c in h1 if str(c).strip())
            s2 = "".join(str(c).strip() for c in h2 if str(c).strip())
            if not s1 or not s2:
                return False
            # 精确Match (overrideall粘连场景)
            if s1 == s2:
                return True
            # 容忍微小差异 (OCR 偶尔丢字/多字)
            if len(s1) > 5 and len(s2) > 5:
                from difflib import SequenceMatcher
                ratio = SequenceMatcher(None, s1, s2).ratio()
                return ratio >= 0.85
            return False

        # ── 顺序分组 ──
        # each group = { "header": [...], "rows": [...], "block": first_block }
        groups = []
        current_group = None

        for block in valid:
            first_row = block.raw_content[0]

            if _is_data_row(first_row):
                # ── 续页: 首行是Data, 加入当前组 ──
                if current_group is None:
                    # 没有当前组 → 无法确定Table header, Skip
                    logger.debug("[ColumnMapper] skip orphan continuation block (no header group)")
                    continue

                col_diff = abs(len(first_row) - len(current_group["header"]))
                if col_diff <= 3: # Changed from 2 to 3
                    for row in block.raw_content:
                        padded = self._pad_row(row, len(current_group["header"]))
                        current_group["rows"].append(padded)
                    logger.info(
                        f"[ColumnMapper] continuation: +{len(block.raw_content)}r "
                        f"into group (header='{current_group['header'][0]}')"
                    )
                else:
                    logger.debug(
                        f"[ColumnMapper] skip cont block: col diff {col_diff} > 2"
                    )
            else:
                # ── 首行是Table header ──
                if current_group is not None and _headers_match(
                    current_group["header"], first_row
                ):
                    # 重复Table header → SkipTable header行, Data行加入当前组
                    for row in block.raw_content[1:]:
                        padded = self._pad_row(row, len(current_group["header"]))
                        current_group["rows"].append(padded)
                    logger.info(
                        f"[ColumnMapper] repeat header merge: +{len(block.raw_content)-1}r"
                    )
                elif current_group is not None and len(block.raw_content) > 2:
                    # Table header不Match但列数兼容 → 弹性Merge (检查Data行含Date)
                    col_diff = abs(len(first_row) - len(current_group["header"]))
                    if col_diff <= 2:
                        sample_rows = block.raw_content[1:4]
                        date_hits = sum(1 for r in sample_rows if _is_data_row(r))
                        if date_hits >= 2:
                            for row in block.raw_content[1:]:
                                padded = self._pad_row(row, len(current_group["header"]))
                                current_group["rows"].append(padded)
                            logger.info(
                                f"[ColumnMapper] elastic merge: +{len(block.raw_content)-1}r "
                                f"(col_diff={col_diff}, date_hits={date_hits})"
                            )
                            continue

                    # 真正不同的 table → Enable新组
                    groups.append(current_group)
                    current_group = {
                        "header": list(first_row),
                        "rows": list(block.raw_content[1:]),
                        "block": block,
                    }
                    logger.info(
                        f"[ColumnMapper] new table group: header='{first_row[:3]}' "
                        f"({len(block.raw_content)-1}r)"
                    )
                else:
                    # 没有当前组 或 块太小不值得弹性Merge → Enable新组
                    if current_group is not None:
                        groups.append(current_group)
                    current_group = {
                        "header": list(first_row),
                        "rows": list(block.raw_content[1:]),
                        "block": block,
                    }

        # 最后一组
        if current_group is not None:
            groups.append(current_group)

        if not groups:
            return []

        if len(groups) > 1:
            logger.info(
                f"[ColumnMapper] {len(groups)} table groups found: "
                + ", ".join(
                    f"group{i}({len(g['rows'])}r)" for i, g in enumerate(groups)
                )
            )
        else:
            logger.info(
                f"[ColumnMapper] 1 table group: {len(groups[0]['rows'])} data rows"
            )

        return groups

    @staticmethod
    def _pad_row(row, target_len):
        """补齐或截断行到目标长度。"""
        row = list(row)
        if len(row) < target_len:
            row += [""] * (target_len - len(row))
        elif len(row) > target_len:
            row = row[:target_len]
        return row

    def _map_columns(
        self,
        raw_headers: List[str],
        extra_aliases: Optional[Dict[str, List[str]]] = None,
    ) -> Tuple[Dict[str, Optional[str]], List[str]]:
        """
        三 layer递进式列Map。

        Args:
            raw_headers: 原始Table headerList
            extra_aliases: Standard名 -> 别名List（含 hints + 机构 scene column_map）；None 时用 config。

        Returns:
            (mapping, unmapped)
            mapping: {raw_header: standard_name or None}
            unmapped: 未Map的Original column nameList
        """
        mapping: Dict[str, Optional[str]] = {}
        used_targets: Set[str] = set()
        unmapped: List[str] = []

        if extra_aliases is None:
            extra_aliases = self.config.get("column_aliases", {})
        # 统一为 standard_name -> list of aliases
        normalized: Dict[str, List[str]] = {}
        for k, v in (extra_aliases or {}).items():
            normalized[k] = list(v) if isinstance(v, list) else ([v] if isinstance(v, str) else [])
        extra_aliases = normalized

        for raw_h in raw_headers:
            raw_clean = raw_h.strip()
            if not raw_clean:
                mapping[raw_h] = None
                continue

            # Skip已知的非Standard列
            if raw_clean in SKIP_COLUMNS:
                mapping[raw_h] = None
                unmapped.append(raw_clean)
                continue

            # Skip借贷分列 (由 split amount 逻辑单独Processing)
            if raw_clean in INCOME_KEYWORDS or raw_clean in EXPENSE_KEYWORDS:
                mapping[raw_h] = None
                continue

            # ── Tier 1: 精确Match ──
            target = self._tier1_exact(raw_clean, used_targets, extra_aliases)
            if target:
                mapping[raw_h] = target
                used_targets.add(target)
                continue

            # ── Tier 2: Fuzzy matching ──
            target = self._tier2_fuzzy(raw_clean, used_targets)
            if target:
                mapping[raw_h] = target
                used_targets.add(target)
                continue

            # ── Tier 2.5: 粘连列名子串Match ──
            # Processing char-level Extract导致的列名粘连, 如 "序号Transaction date" contains "Transaction date"
            target = self._tier25_merged(raw_clean, used_targets)
            if target:
                mapping[raw_h] = target
                used_targets.add(target)
                continue

            # ── Tier 3: LLM (预留) ──
            mapping[raw_h] = None
            unmapped.append(raw_clean)

        return mapping, unmapped

    def _tier1_exact(
        self,
        raw: str,
        used: Set[str],
        extra_aliases: Dict[str, List[str]],
    ) -> Optional[str]:
        """精确Match: Standard名 + 别名。"""
        # 直接Match TARGET_COLUMNS
        for target in TARGET_COLUMNS:
            if target not in used and raw == target:
                return target

        # Alias matching
        all_aliases = dict(COLUMN_ALIASES)
        for t, aliases in extra_aliases.items():
            if t in all_aliases:
                all_aliases[t] = list(set(all_aliases[t] + aliases))
            else:
                all_aliases[t] = aliases

        for target, aliases in all_aliases.items():
            if target in used:
                continue
            for alias in aliases:
                if raw == alias:
                    return target

        return None

    def _tier2_fuzzy(self, raw: str, used: Set[str]) -> Optional[str]:
        """
        Fuzzy matching: 子串contains + 编辑距离。

        Optimize: 优先子串contains (高精度)，再用编辑距离兜底。
        """
        best_target = None
        best_score = 0.0

        for target, aliases in COLUMN_ALIASES.items():
            if target in used:
                continue

            # 子串contains
            all_candidates = [target] + aliases
            for cand in all_candidates:
                # 短词护栏: ≤3字符的候选词要求高Match率, avoid误Match
                if len(cand) <= 3 or len(raw) <= 3:
                    if cand == raw:
                        score = 1.0
                    elif cand in raw and len(cand) >= len(raw) * 0.5:
                        score = len(cand) / len(raw)
                    elif raw in cand and len(raw) >= len(cand) * 0.5:
                        score = len(raw) / len(cand)
                    else:
                        continue
                elif cand in raw or raw in cand:
                    score = len(min(cand, raw, key=len)) / len(max(cand, raw, key=len))
                else:
                    continue
                if score > best_score:
                    best_score = score
                    best_target = target

            # 编辑距离 (仅对短串)
            if len(raw) <= 10:
                for cand in all_candidates:
                    if len(cand) <= 10:
                        dist = self._edit_distance(raw, cand)
                        max_len = max(len(raw), len(cand))
                        score = 1.0 - dist / max_len if max_len > 0 else 0.0
                        if score > best_score:
                            best_score = score
                            best_target = target

        return best_target if best_score >= 0.6 else None

    def _tier25_merged(self, raw: str, used: Set[str]) -> Optional[str]:
        """
        粘连列名子串Match。

        Processing char-level Extract中多个列名粘连为一个字符串的场景。
        例e.g.: "序号Transaction date" contains "Transaction date", "凭证种类DebitTransaction amount" contains "DebitTransaction amount"

        策略: 优先Match最长的候选 (avoid短词误命中)
        """
        if len(raw) <= 4:
            # 太短不做粘连Split
            return None

        best_target = None
        best_len = 0

        # 检查Standard column name及其别名Whether为 raw 的子串
        for target, aliases in COLUMN_ALIASES.items():
            if target in used:
                continue
            all_candidates = [target] + aliases
            for cand in all_candidates:
                if len(cand) >= 2 and cand in raw and len(cand) > best_len:
                    best_len = len(cand)
                    best_target = target

        # 也检查 INCOME/EXPENSE 关键字
        if best_target is None:
            for kw in INCOME_KEYWORDS | EXPENSE_KEYWORDS:
                if kw in raw and len(kw) > best_len:
                    # 不Map到Standard列, 交给 split amount Processing
                    return None

        if best_target and best_len >= 2:
            logger.debug(
                f"[ColumnMapper] tier2.5 merged match: "
                f"'{raw}' → '{best_target}' (substr len={best_len})"
            )

        return best_target

    # ═══════════════════════════════════════════════════════════════════════════
    # Header-Data Alignment — 委托给 header_alignment Module
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _infer_column_type(
        data_rows: List[List[str]], col_idx: int, sample_size: int = 30,
    ) -> Dict[str, float]:
        """推断单列DataType分布 — 委托给 header_alignment Module。"""
        return infer_column_type(data_rows, col_idx, sample_size)

    def _verify_header_data_alignment(
        self,
        headers: List[str],
        data_rows: List[List[str]],
        result: "EnhancedResult",
    ) -> List[str]:
        """ValidateTable header与Data列Alignment — 委托给 header_alignment Module。"""
        return verify_header_data_alignment(
            headers=headers,
            data_rows=data_rows,
            header_type_expectations=_HEADER_TYPE_EXPECTATIONS,
            mutation_recorder=result,
            middleware_name=self.name,
        )

    def _detect_split_amount(
        self, headers: List[str], mapping: Dict[str, Optional[str]],
        data_rows: Optional[List[List[str]]] = None,
    ) -> Tuple[bool, Optional[int], Optional[int]]:
        """Detect收入/支出分列 — 委托给 amount_splitter Module。"""
        return _detect_split_amount_fn(
            headers=headers,
            mapping=mapping,
            income_keywords=INCOME_KEYWORDS,
            expense_keywords=EXPENSE_KEYWORDS,
            amount_like_keywords=AMOUNT_LIKE_KEYWORDS,
            data_rows=data_rows,
        )

    def _standardize(
        self,
        raw_headers: List[str],
        data_rows: List[List[str]],
        mapping: Dict[str, Optional[str]],
        has_split_amount: bool,
        split_income_idx: Optional[int],
        split_expense_idx: Optional[int],
        block_id: str,
        result: EnhancedResult,
    ) -> List[List[str]]:
        """
        生成Standard化Table — retainOriginal column name和allData。

        仅做两项Standard化:
            1. 收入/支出分列Merge为单一带符号Amount column
            2. Date/Amount单元格清洗
        """
        # ── 建立Table header ──
        out_headers = list(raw_headers)

        # 记录列Map mutation (仅记录, 不用于重建 table结构)
        for rh, target in mapping.items():
            if target and rh != target:
                result.record_mutation(
                    middleware_name=self.name,
                    target_block_id=block_id,
                    field_changed="column_name",
                    old_value=rh,
                    new_value=target,
                    confidence=0.9,
                    reason="column_mapping",
                )

        # ── 收入/支出分列定位 ──
        income_idx = split_income_idx
        expense_idx = split_expense_idx

        if has_split_amount and income_idx is None:
            for i, h in enumerate(raw_headers):
                h_clean = h.strip()
                if h_clean in INCOME_KEYWORDS:
                    income_idx = i
                elif h_clean in EXPENSE_KEYWORDS:
                    expense_idx = i

        # ── 动态查找Date/Amount/Balance列Index (用于单元格清洗) ──
        date_col_idx = self._find_col_idx(raw_headers, mapping, "交易时间")
        amount_col_idx = self._find_col_idx(raw_headers, mapping, "Transaction amount")
        balance_col_idx = self._find_col_idx(raw_headers, mapping, "AccountBalance")

        # ── 构建Data行 ──
        std_rows = [out_headers]

        for row in data_rows:
            out_row = [str(cell).strip() if cell else "" for cell in row]
            # 补齐或截断到Table header长度
            if len(out_row) < len(out_headers):
                out_row += [""] * (len(out_headers) - len(out_row))
            elif len(out_row) > len(out_headers):
                out_row = out_row[:len(out_headers)]

            # Merge收入/支出到Amount column
            if has_split_amount and income_idx is not None and expense_idx is not None:
                if amount_col_idx is not None:
                    target_idx = amount_col_idx
                else:
                    # 没有现成Amount column → 用收入列位置
                    target_idx = income_idx

                income_val = row[income_idx].strip() if income_idx < len(row) else ""
                expense_val = row[expense_idx].strip() if expense_idx < len(row) else ""

                income_num = self._parse_amount(income_val)
                expense_num = self._parse_amount(expense_val)

                if expense_num and abs(expense_num) > 0.001:
                    out_row[target_idx] = f"-{abs(expense_num):.2f}"
                elif income_num and abs(income_num) > 0.001:
                    out_row[target_idx] = f"{income_num:.2f}"
                else:
                    out_row[target_idx] = "0.00"

                # Fix B: 清空原始借贷列 (非 target 列), preventalso出现收入+支出
                if target_idx != income_idx and income_idx < len(out_row):
                    out_row[income_idx] = ""
                if target_idx != expense_idx and expense_idx < len(out_row):
                    out_row[expense_idx] = ""

            # 单元格清洗: Date/Amount column
            out_row = self._clean_std_row(out_row, date_col_idx, amount_col_idx, balance_col_idx)

            std_rows.append(out_row)

        return std_rows

    # ── Date/Amount正则 (编译一次复用) ──
    _RE_DATE = re.compile(r'(\d{4}[-/.]?\d{2}[-/.]?\d{2})')
    _RE_AMOUNT = re.compile(r'^([+-]?\d[\d,]*\.?\d*)')

    @staticmethod
    def _find_col_idx(
        headers: List[str],
        mapping: Dict[str, Optional[str]],
        target_name: str,
    ) -> Optional[int]:
        """via column_mapping 反查原始列Index。"""
        for i, h in enumerate(headers):
            if mapping.get(h) == target_name:
                return i
            if h.strip() == target_name:
                return i
        return None

    def _clean_std_row(
        self,
        row: List[str],
        date_idx: Optional[int],
        amount_idx: Optional[int],
        balance_idx: Optional[int],
    ) -> List[str]:
        """
        按列Type清洗行 (动态Index)。

        - Date列: 只retainDatepartial (YYYY-MM-DD)
        - Amount/Balance列: 只retain数值partial
        """
        # Fix A: Date列 — Extract YYYY-MM-DD 并retain时间partial
        if date_idx is not None and date_idx < len(row) and row[date_idx]:
            m = self._RE_DATE.search(row[date_idx])
            if m:
                d = m.group(1).replace("/", "-").replace(".", "-")
                if len(d) == 8 and "-" not in d:
                    d = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
                # retainDate后的时间 (HH:MM 或 HH:MM:SS)
                after = row[date_idx][m.end():]
                time_m = re.search(r'\d{2}:\d{2}(?::\d{2})?', after)
                if time_m:
                    d = f"{d} {time_m.group()}"
                row[date_idx] = d

        # Amount column & Balance列: 只retain数值
        for idx in (amount_idx, balance_idx):
            if idx is not None and idx < len(row):
                val = row[idx].strip()
                if val:
                    cleaned = val.replace(",", "").replace("，", "").replace("¥", "")
                    m = self._RE_AMOUNT.match(cleaned)
                    if m:
                        try:
                            row[idx] = f"{float(m.group(1)):.2f}"
                        except ValueError:
                            row[idx] = ""
                    else:
                        row[idx] = ""

        return row

    @staticmethod
    def _is_number(s: str) -> bool:
        """检查字符串Whether为数字。"""
        try:
            float(s.replace(",", "").replace("，", ""))
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _parse_amount(s: str) -> Optional[float]:
        """ParseAmount字符串为 float，FailedReturns None。"""
        if not s or not s.strip():
            return None
        try:
            return float(s.strip().replace(",", "").replace("，", ""))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _edit_distance(s1: str, s2: str) -> int:
        """Levenshtein 编辑距离。"""
        if len(s1) < len(s2):
            return ColumnMapper._edit_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        prev = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            curr = [i + 1]
            for j, c2 in enumerate(s2):
                cost = 0 if c1 == c2 else 1
                curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
            prev = curr
        return prev[-1]
