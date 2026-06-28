"""Financial statement table structure reconstruction."""

from docmirror.tables.statement.column_groups import build_column_groups
from docmirror.tables.statement.header_bands import build_header_bands
from docmirror.tables.statement.note_refs import extract_note_ref, normalize_note_ref
from docmirror.tables.statement.reconstructor import build_statement_structure
from docmirror.tables.statement.row_hierarchy import build_account_rows
from docmirror.tables.statement.rules import build_statement_rules

__all__ = [
    "build_account_rows",
    "build_column_groups",
    "build_header_bands",
    "build_statement_rules",
    "build_statement_structure",
    "extract_note_ref",
    "normalize_note_ref",
]
