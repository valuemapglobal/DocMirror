"""
OFD adapter subpackage — Chinese Open Fixed-layout Document extraction.

Re-exports ``OFDAdapter`` for e-invoice, fiscal receipt, and e-license OFD
files parsed as ZIP/XML text containers.
"""

from .ofd import OFDAdapter

__all__ = ["OFDAdapter"]
