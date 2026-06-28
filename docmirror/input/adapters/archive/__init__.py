"""
Archive adapter subpackage — batch ZIP and RAR extraction.

Re-exports ``ArchiveAdapter`` which decompresses container files and recursively
dispatches supported child documents through the full parse pipeline.
"""

from .archive import ArchiveAdapter

__all__ = ["ArchiveAdapter"]
