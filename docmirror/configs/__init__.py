"""
DocMirror Configuration Package
================================

Provides centralized configuration for the DocMirror parsing engine.
Exports:
    - DocMirrorSettings: Global configuration dataclass with env var overrides.
    - default_settings: Pre-initialized singleton loaded from current environment.
"""
from .settings import DocMirrorSettings, default_settings

__all__ = ["DocMirrorSettings", "default_settings"]
