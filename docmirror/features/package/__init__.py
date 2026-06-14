"""Multi-file package intelligence."""

from docmirror.features.package.consistency import ConsistencyHypothesis, evaluate_package_consistency
from docmirror.features.package.manifest import PackageManifest, check_package_consistency

__all__ = [
    "PackageManifest",
    "check_package_consistency",
    "ConsistencyHypothesis",
    "evaluate_package_consistency",
]
