"""
Post-extract hook implementations package.

Contains concrete ``PostExtractHook`` subclasses registered in ``post_extract.yaml``.
Not imported directly by callers — the catalog loader resolves modules by path.

Pipeline role: hook modules are loaded dynamically after PEC extract; see individual
hook files for domain-specific behavior.
"""
