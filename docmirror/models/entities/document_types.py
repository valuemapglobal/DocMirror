"""
MultiModal 证照与Document Schema define
"""

from enum import Enum
from typing import Dict

class DocumentType(str, Enum):
    """DocumentTypeEnum"""
    FINANCIAL_REPORT = "financial_report"  # 财务报告
    INVOICE = "invoice"  # Invoice
    CONTRACT = "contract"  # Contract
    BANK_STATEMENT = "bank_statement"  # Bank statement
    TAX_REPORT = "tax_report"  # 税务报告
    BUSINESS_LICENSE = "business_license"  # Business license
    ID_CARD = "id_card"  # ID card
    OTHER = "other"  # Other

# 各DocumentType的Field Schema
DOCUMENT_FIELD_SCHEMAS: Dict[DocumentType, Dict[str, str]] = {
    DocumentType.FINANCIAL_REPORT: {
        "company_name": "企业Name",
        "report_period": "报告Period",
        "report_type": "报告Type（年报/季报/月报）",
        "total_revenue": "营业总收入",
        "operating_cost": "营业成本",
        "gross_profit": "毛利润",
        "net_profit": "净利润",
        "total_assets": "总资产",
        "total_liabilities": "总负债",
        "owner_equity": "all者权益",
        "cash_and_equivalents": "货币资金",
        "accounts_receivable": "应收账款",
        "inventory": "存货",
        "fixed_assets": "固定资产",
        "accounts_payable": "应付账款",
        "short_term_loan": "短期借款",
        "long_term_loan": "长期借款",
        "operating_cash_flow": "经营活动现金流量净额",
        "investing_cash_flow": "投资活动现金流量净额",
        "financing_cash_flow": "筹资活动现金流量净额",
    },
    DocumentType.INVOICE: {
        "invoice_code": "Invoice代码",
        "invoice_number": "Invoice number",
        "invoice_date": "Invoice date",
        "buyer_name": "BuyerName",
        "buyer_tax_id": "Buyer纳税人Recognize号",
        "seller_name": "SellerName",
        "seller_tax_id": "Seller纳税人Recognize号",
        "items": "商品或服务明细",
        "amount_without_tax": "不含税Amount",
        "tax_amount": "Tax amount",
        "total_amount": "Total with tax",
        "invoice_type": "InvoiceType",
    },
    DocumentType.BANK_STATEMENT: {
        "account_name": "Account name称",
        "account_number": "Account number",
        "bank_name": "Bank name",
        "statement_period": "账单周期",
        "opening_balance": "期初Balance",
        "closing_balance": "期末Balance",
        "total_deposits": "存入总额",
        "total_withdrawals": "支出总额",
        "transaction_count": "交易笔数",
    },
    DocumentType.BUSINESS_LICENSE: {
        "company_name": "企业Name",
        "unified_social_credit_code": "统一社会信用代码",
        "legal_representative": "法定代 table人",
        "registered_capital": "Register资本",
        "establishment_date": "成立Date",
        "business_term": "营业期限",
        "registered_address": "住所",
        "business_scope": "经营范围",
        "company_type": "公司Type",
    },
    DocumentType.CONTRACT: {
        "contract_title": "ContractTitle",
        "contract_number": "Contract number",
        "party_a": "Party A",
        "party_b": "Party B",
        "signing_date": "Signing date",
        "effective_date": "生效Date",
        "expiry_date": "到期Date",
        "contract_amount": "Contract amount",
        "payment_terms": "付款条款",
        "contract_subject": "Contract标的",
    },
    DocumentType.TAX_REPORT: {
        "taxpayer_name": "纳税人Name",
        "taxpayer_id": "纳税人Recognize号",
        "tax_period": "税款所属期",
        "tax_type": "税种",
        "taxable_income": "应纳税所得额",
        "tax_rate": "Tax rate",
        "tax_amount": "应纳Tax amount",
        "tax_paid": "已缴Tax amount",
        "tax_due": "应补（退）Tax amount",
    },
    DocumentType.ID_CARD: {
        "name": "姓名",
        "gender": "性别",
        "ethnicity": "民族",
        "birth_date": "出生Date",
        "address": "住址",
        "id_number": "ID card号码",
        "issuing_authority": "签发机关",
        "valid_period": "有效期限",
    },
    DocumentType.OTHER: {
        "title": "Title",
        "content_summary": "内容Abstract/Summary",
        "key_information": "关键Information",
    },
}
