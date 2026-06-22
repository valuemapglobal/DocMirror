"""Deployment health and capability introspection.

Provides the canonical health-check shape used by ``GET /health`` (Docker /
REST), offline verification, and integration readiness reports.  Every
deployment surface (CPU Docker, GPU Docker, offline air-gapped) returns
the same structured ``HealthReport`` so operators don't need surface-specific
monitoring scripts.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field, asdict
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path
from typing import Any


def _get_version(package_name: str = "docmirror") -> str:
    """Return the installed package version, or ``'unknown'``."""
    try:
        return pkg_version(package_name)
    except PackageNotFoundError:
        try:
            return pkg_version("docmirror-base")
        except PackageNotFoundError:
            return "unknown"


def _detect_device() -> str:
    """Best-effort device detection: ``cpu`` or ``gpu``."""
    try:
        import torch  # type: ignore[import-untyped]
        if torch.cuda.is_available():
            return "gpu"
    except Exception:
        pass
    return "cpu"


def _detect_offline() -> bool:
    """Return True when no outbound internet is reachable."""
    import socket
    try:
        sock = socket.create_connection(("8.8.8.8", 53), timeout=1.0)
        sock.close()
        return False
    except OSError:
        return True


def _check_models(models_dir: str | None = None) -> dict[str, bool]:
    """Check presence of expected OCR / model directories."""
    candidates = [
        (models_dir or str(Path.home() / ".cache" / "docmirror" / "models")),
        str(Path(__file__).resolve().parents[3] / "models"),
        "/opt/docmirror/models",
    ]
    for path in candidates:
        p = Path(path)
        if p.is_dir():
            files = list(p.glob("*"))
            if files:
                return {"available": True, "path": str(p), "files": len(files)}
    return {"available": False, "path": None, "files": 0}


@dataclass
class HealthReport:
    """Canonical health-check payload returned by every DocMirror deployment.

    Shape is intentionally small so it is cheap to poll from orchestrators.
    """

    status: str = "ok"            # ok | degraded | unavailable
    version: str = ""
    device: str = "cpu"
    offline_ready: bool = False
    capabilities: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None and v != []}


def build_health_report() -> HealthReport:
    """Construct a health report reflecting the current runtime environment.

    Used by ``GET /health``, Docker healthchecks, and CLI ``docmirror server
    start`` so operators get a uniform view.
    """
    ver = _get_version()
    device = _detect_device()
    offline = _detect_offline()
    models = _check_models()

    warnings: list[str] = []
    status = "ok"

    offline_ready = offline or models.get("available", False)
    if not offline_ready:
        status = "degraded"
        warnings.append("Model cache not found; offline readiness not guaranteed.")

    capabilities = {
        "formats": ["json", "markdown", "chunks", "evidence", "parquet", "html"],
        "editions": ["mirror", "community", "enterprise", "finance"],
        "profiles": ["compact", "full", "forensic", "ga_full"],
        "modes": ["auto", "fast", "balanced", "accurate", "forensic"],
        "features": ["ocr", "table_extraction", "structure_analysis", "layout_detection"],
    }

    return HealthReport(
        status=status,
        version=ver,
        device=device,
        offline_ready=offline_ready,
        capabilities=capabilities,
        warnings=warnings,
    )


def health_check() -> dict[str, Any]:
    """One-call health introspection (used by Docker HEALTHCHECK CMD)."""
    return build_health_report().to_dict()
