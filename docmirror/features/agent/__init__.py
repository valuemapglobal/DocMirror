"""
Agent routing layer (L11) — consumes EFPA outputs without mutating parsing.

Re-exports ``DocumentRoute`` and ``route_document`` for workflows that need
parse-path recommendations after a document has been perceived. Safe to call
from orchestration code that sits above the core ``perceive_document`` API.
"""

from docmirror.features.agent.router import DocumentRoute, route_document

__all__ = ["DocumentRoute", "route_document"]
