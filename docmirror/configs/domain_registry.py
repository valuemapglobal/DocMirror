"""
Domain Registry — Document-type-specific identity field definitions.
=====================================================================

Maps each document type (e.g., bank_statement, invoice, contract) to a list
of identity field definitions. Each definition specifies:

    (display_name, candidate_key_1, candidate_key_2, ...)

The ``resolve_identity()`` function looks up fields for a given domain,
then searches the provided entities dict for the first matching candidate
key that has a non-empty value. This allows flexible extraction from
documents where the same concept may appear under different key names
(e.g., "Account holder", "Card holder", "Customer name" all map to
the "account_holder" identity field).

The wildcard domain ``"*"`` serves as a fallback for unrecognized
document types, providing minimal identity extraction (title, date, author).

Usage::

    from docmirror.configs.domain_registry import resolve_identity

    identity = resolve_identity("bank_statement", extracted_entities)
    # {'document_type': 'bank_statement', 'institution': 'HSBC', ...}
"""

from typing import Any, Dict, List, Tuple


# Document type → list of identity field definitions.
# Each tuple: (display_name, candidate_key_1, candidate_key_2, ...)
# The resolver tries candidate keys in order and uses the first non-empty match.
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
    # Wildcard fallback — used for any unrecognized document type
    "*": [
        ("title", "Title", "Title"),
        ("date", "Date", "Date"),
        ("author", "Author", "Author"),
    ],
}


def resolve_identity(domain: str, entities: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract standardized identity fields from raw entities by document type.

    For each identity field defined in the domain's DOMAIN_IDENTITY entry,
    iterates through the candidate keys and picks the first one that has
    a non-empty value in the entities dict. Falls back to the wildcard
    ``"*"`` domain if the specific domain is not registered.

    Args:
        domain:   Document type string (e.g., "bank_statement", "invoice").
        entities: Dict of extracted key-value entities from the document.

    Returns:
        Dict with standardized identity fields. Always includes
        ``"document_type"`` as the first key. Missing fields are set
        to empty strings.
    """
    fields = DOMAIN_IDENTITY.get(domain, DOMAIN_IDENTITY.get("*", []))
    identity: Dict[str, str] = {"document_type": domain}

    for field_def in fields:
        display_name = field_def[0]
        candidates = field_def[1:]
        # Try each candidate key in order; use the first non-empty value
        for key in candidates:
            val = entities.get(key, "")
            if val:
                identity[display_name] = str(val)
                break
        else:
            # No candidate had a value — set to empty string
            identity[display_name] = ""

    return identity
