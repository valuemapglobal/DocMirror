"""
Multi-file package intelligence — manifest and consistency APIs.

Re-exports manifest construction and cross-file consistency evaluation helpers
for batch uploads and agent workflows that treat related files as a single
logical package.
"""

from docmirror.features.package.consistency import ConsistencyHypothesis, evaluate_package_consistency
from docmirror.features.package.manifest import PackageManifest, check_package_consistency

__all__ = [
    "PackageManifest",
    "check_package_consistency",
    "ConsistencyHypothesis",
    "evaluate_package_consistency",
]
