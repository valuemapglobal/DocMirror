"""Canonical ParseResult assembly owned by the fact pipeline."""

from .assembler import assemble_parse_result, attach_parse_policy
from .page_assembler import assemble_pages

__all__ = ["assemble_pages", "assemble_parse_result", "attach_parse_policy"]
