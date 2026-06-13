"""Multi-file package intelligence."""

from docmirror.core.package.consistency import ConsistencyHypothesis, evaluate_package_consistency
from docmirror.core.package.manifest import PackageManifest, check_package_consistency

__all__ = [
    "PackageManifest",
    "check_package_consistency",
    "ConsistencyHypothesis",
    "evaluate_package_consistency",
]
