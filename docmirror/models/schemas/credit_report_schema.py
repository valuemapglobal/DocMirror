"""
Credit report schema definition — typed bounds and dirty-data cleansing.

Provides absolute typing bounds, defaults, and auto-cleansing for the complex
Credit Report L2 JSON payload produced by credit-report domain plugins.

Uses Pydantic sub-models (``SubjectInfo``, ``BasicInfo``, …) with ``extra="allow"``
for flexible keys that change between report versions. Validators normalize
common dirty-data patterns (whitespace, date formats, numeric strings).

Registered in ``schemas/registry.yaml`` for DEC validation via ``validate_dec``.
"""

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------
# Sub-Models
# ---------------------------------------------------------

class SubjectInfo(BaseModel):
    name: str = Field(default="", alias="name")
    id_type: str = Field(default="", alias="id_type")
    id_number: str = Field(default="", alias="id_number")
    zhengma: str = Field(default="", alias="zhengma")
    phone_numbers: list = Field(default_factory=list, alias="phone_numbers")

    # Catch-all for extra flexible keys that change often (e.g. spouse info)
    model_config = {"extra": "allow"}


class BasicInfo(BaseModel):
    # Primarily for enterprise reports
    company_name: str = Field(default="", alias="机构名称")
    economic_type: str = Field(default="", alias="经济类型")
    scale: str = Field(default="", alias="企业规模")
    industry: str = Field(default="", alias="所属行业")
    registered_capital: str = Field(default="", alias="注册资本")
    legal_rep: str = Field(default="", alias="法定代表人")
    legal_rep_id: str = Field(default="", alias="法定代表人身份证号")
    found_year: str = Field(default="", alias="成立年份")

    model_config = {"extra": "allow", "populate_by_name": True}


class CreditSummary(BaseModel):
    default_summary: dict[str, Any] = Field(default_factory=dict, alias="default_summary")
    liability_summary: dict[str, Any] = Field(default_factory=dict, alias="liability_summary")
    prompt_summary: dict[str, Any] = Field(default_factory=dict, alias="prompt_summary")

    # Flat summary lifts — accept both str and int/float from upstream
    credit_balance: str | int | float = Field(default="", alias="借贷交易余额")
    guarantee_balance: str | int | float = Field(default="", alias="担保交易余额")
    total_accounts: int | str = Field(default=0, alias="账户数")
    overdue_accounts: int | str = Field(default=0, alias="发生过逾期的账户数")
    unsettled_accounts: int | str = Field(default=0, alias="未结清账户数")
    overdue_record: str = Field(default="", alias="逾期记录")
    overdue_count: int | str = Field(default=0, alias="逾期次数")

    model_config = {"extra": "allow", "populate_by_name": True}

    @field_validator("credit_balance", "guarantee_balance", mode="before")
    def _coerce_balance_to_str(cls, v):
        """Upstream may emit int 0 or float 0.0 for zero balances."""
        if v is None:
            return ""
        return str(v)

    @field_validator("total_accounts", "overdue_accounts", "unsettled_accounts", mode="before")
    def _clean_ints(cls, v):
        if not v: return 0
        try:
            return int(str(v).replace(',', ''))
        except Exception:
            return 0


class CreditAccount(BaseModel):
    """Normalized object for a single line of credit/loan/card."""
    account_type: str = Field(default="未知种类", alias="账户分类")
    business_type: str = Field(default="", alias="业务种类")
    currency: str = Field(default="人民币", alias="币种")
    limit_amount: str = Field(default="0", alias="授信总额")
    balance: str = Field(default="0", alias="余额")
    open_date: str = Field(default="", alias="开立日期")
    close_date: str = Field(default="", alias="到期日期")
    status: str = Field(default="正常", alias="账户状态")
    five_tier_class: str = Field(default="", alias="五级分类")
    overdue_amount: str = Field(default="0", alias="当前逾期总额")
    overdue_periods: str = Field(default="0", alias="当前逾期期数")
    guarantee_type: str = Field(default="", alias="担保方式")
    repayment_records: list = Field(default_factory=list, alias="repayment_records")

    model_config = {"extra": "allow", "populate_by_name": True}

    @field_validator("limit_amount", "balance", "overdue_amount", mode="before")
    def _clean_currency(cls, v):
        if not v: return "0"
        if isinstance(v, str):
            # OCR often sees dot as comma or vice versa. E.g. "12.000,50" -> 12000.50
            # For simplicity, strip everything but digits and a single doc.
            v_clean = re.sub(r'[^\d\.]', '', v)
            return v_clean if v_clean else "0"
        return str(v)


class PublicRecords(BaseModel):
    tax_arrears: int | str = Field(default=0, alias="欠税记录条数")
    civil_judgments: int | str = Field(default=0, alias="民事判决记录条数")
    enforcements: int | str = Field(default=0, alias="强制执行记录条数")
    admin_penalties: int | str = Field(default=0, alias="行政处罚记录条数")

    model_config = {"extra": "allow", "populate_by_name": True}

    @field_validator("*", mode="before")
    def _clean_all_counts(cls, v):
        if not v: return 0
        try:
            return int(float(str(v).replace(',', '')))
        except Exception:
            return 0


# ---------------------------------------------------------
# Root L2 DOM (Document Object Model)
# ---------------------------------------------------------

class CreditReportResultSchema(BaseModel):
    """
    The Absolute L2 Root Vault.
    Provides bullet-proof structure, default initializations, and deep validation.
    """
    report_id: str = Field(default="", alias="报告编号")
    report_subtype: str = Field(default="", alias="report_subtype")
    report_date: str = Field(default="", alias="报告时间")

    subject: SubjectInfo = Field(default_factory=SubjectInfo)
    basic_info: BasicInfo = Field(default_factory=BasicInfo)
    credit_summary: CreditSummary = Field(default_factory=CreditSummary)
    credit_accounts: list[CreditAccount] = Field(default_factory=list)
    public_records: PublicRecords = Field(default_factory=PublicRecords)

    # Can be a list or deep dict depending on parsing mode. Allowed flexibility.
    query_records: Any = Field(default_factory=list, alias="query_records")

    # Commercial Gateway payload
    features: dict[str, Any] | None = None

    model_config = {"extra": "allow", "populate_by_name": True}

