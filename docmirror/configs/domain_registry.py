"""
Domain registry — register identity fields by document type
==========================================

Replaces hardcoded bank statement fields in to_api_dict().
To extend: add a new domain to DOMAIN_IDENTITY.
"""

from typing import Any, Dict, List, Tuple


# domain_type → [(display_name, candidate_key1, candidate_key2, ...)]
DOMAIN_IDENTITY: Dict[str, List[Tuple[str, ...]]] = {
    "bank_statement": [
        ("institution", "bank_name", "Bank name", "Bank branch"),
        ("account_holder", "Account name", "Account name", "Account name", "Account holder", "Card holder", "Customer name", "Customer name"),
        ("account_number", "Account number", "Card number", "Account", "Customer account number"),
        ("query_period", "Query period", "Period", "From/to date"),
        ("currency", "Currency"),
        ("print_date", "Print date"),
    ],
    "invoice": [
        ("supplier", "Supplier", "Seller", "Invoice issuer"),
        ("buyer", "Buyer", "Buyer", "Invoice receiver"),
        ("invoice_no", "Invoice number", "Invoice number", "Invoice No"),
        ("amount", "Amount", "Total amount", "Total with tax"),
        ("tax", "Tax amount", "Tax rate"),
        ("date", "Invoice date", "Date"),
    ],
    "contract": [
        ("party_a", "Party A", "Party A"),
        ("party_b", "Party B", "Party B"),
        ("contract_no", "Contract number", "Contract No"),
        ("sign_date", "Signing date", "Signing date"),
        ("amount", "Contract amount", "Amount"),
    ],
    "receipt": [
        ("merchant", "Merchant name", "Merchant", "Merchant"),
        ("amount", "Transaction amount", "Amount", "Amount"),
        ("date", "Transaction date", "Date", "Date"),
    ],
    # 通配 fallback
    "*": [
        ("title", "Title", "Title"),
        ("date", "Date", "Date"),
        ("author", "Author", "Author"),
    ],
}


def resolve_identity(domain: str, entities: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract standardized identity fields from entities based on domain type.

    Args:
        domain:   Document type (bank_statement, invoice, contract, ...)
        entities: Extracted key-value entities

    Returns:
        Standardized identity dict {display_name: value}
    """
    fields = DOMAIN_IDENTITY.get(domain, DOMAIN_IDENTITY.get("*", []))
    identity: Dict[str, str] = {"document_type": domain}

    for field_def in fields:
        display_name = field_def[0]
        candidates = field_def[1:]
        for key in candidates:
            val = entities.get(key, "")
            if val:
                identity[display_name] = str(val)
                break
        else:
            identity[display_name] = ""

    return identity
