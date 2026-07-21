# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""InputAcceptance — unified pre-dispatcher probe, gate, and decision pipeline.

Usage::

    from docmirror.input.acceptance import check_input_acceptance

    report = check_input_acceptance(path)
    if not report.decision.accepted:
        # Build failure ParseResult with error code from report
        ...
    # else proceed to dispatcher
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import filetype

from docmirror.configs.format.resolver import resolve_capability
from docmirror.configs.runtime.settings import DocMirrorSettings
from docmirror.configs.support_matrix import support_for_capability
from docmirror.input.archive_probe import probe_archive
from docmirror.input.image_probe import probe_image
from docmirror.input.models import (
    AcceptedSource,
    CapabilityReport,
    InputAcceptanceReport,
    InputDecisionReport,
    InputProbeReport,
    InputRejectedError,
    ResourceGateReport,
    SafetyGateReport,
)
from docmirror.input.pdf_probe import probe_pdf

logger = logging.getLogger(__name__)


from docmirror.configs.runtime.yaml_loader import config_loader


def _build_input_probe(path: Path) -> InputProbeReport:
    """Build basic file identity probe."""
    report = InputProbeReport()
    report.file_name = path.name
    report.extension = path.suffix.lower()
    report.exists = path.is_file()
    if report.exists:
        stat = path.stat()
        report.size_bytes = stat.st_size
        detected = filetype.guess(str(path))
        report.mime_type = detected.mime if detected else ""
        try:
            digest = hashlib.sha256()
            with open(path, "rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            report.checksum = digest.hexdigest()
            report.readable = True
        except OSError:
            report.readable = False
    return report


def _build_resource_gate(
    path: Path,
    probe_report: InputProbeReport,
    settings: DocMirrorSettings | None = None,
) -> ResourceGateReport:
    """Check file size and image resolution against resource limits."""
    report = ResourceGateReport()

    # Read resource limits directly from YAML input_acceptance section
    iac_config = config_loader.get("input_acceptance", {})
    min_size = iac_config.get("min_file_size_bytes", 100)
    max_size = iac_config.get("max_file_size_bytes", 524288000)

    report.limits["min_file_size_bytes"] = min_size
    report.limits["max_file_size_bytes"] = max_size
    report.actual["size_bytes"] = probe_report.size_bytes

    if probe_report.size_bytes < min_size:
        report.status = "fail"
        report.violations.append(f"FILE_TOO_SMALL: {probe_report.size_bytes} bytes < {min_size} min")
    elif probe_report.size_bytes > max_size:
        report.status = "fail"
        report.violations.append(f"FILE_TOO_LARGE: {probe_report.size_bytes} bytes > {max_size} max")

    # Image pixel budget check
    max_pixels = iac_config.get("max_image_pixels", 100_000_000)
    report.limits["max_image_pixels"] = max_pixels

    return report


def _build_safety_gate(
    path: Path,
    probe_report: InputProbeReport,
) -> SafetyGateReport:
    """Run per-transport safety probes."""
    report = SafetyGateReport()
    ext = probe_report.extension

    if ext == ".pdf":
        pdf_result = probe_pdf(path)
        report.checks["pdf_probe_status"] = pdf_result.status
        if pdf_result.status == "encrypted":
            report.status = "fail"
            report.checks["error_code"] = "ENCRYPTED_PDF"
        elif pdf_result.status == "damaged":
            report.status = "fail"
            report.checks["error_code"] = "DAMAGED_PDF"

    elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"):
        img_result = probe_image(path)
        report.checks["image_probe_status"] = img_result.status
        if img_result.status in ("invalid", "low_quality"):
            report.status = "fail"
            report.checks["error_code"] = img_result.error_code

    elif ext == ".zip":
        archive_result = probe_archive(path)
        report.checks["archive_probe_status"] = archive_result.status
        if archive_result.status in ("password", "resource_limit", "unsafe"):
            report.status = "fail"
            report.checks["error_code"] = archive_result.error_code

    if report.status == "pass" and report.checks:
        report.checks["all_safe"] = True

    return report


def _build_capability_report(path: Path, known_mime: str = "") -> CapabilityReport:
    """Resolve FCR capability and support matrix info."""
    report = CapabilityReport()
    try:
        cap = resolve_capability(path, known_mime)
        sm = support_for_capability(cap.id)
        report.id = cap.id
        report.transport = cap.transport
        report.support_status = sm.get("ga_status", cap.status)
        report.requires_converter = sm.get("requires_converter")
        report.requires_dependency = sm.get("dependencies", [])
        report.limitations = sm.get("limitations", [])
    except Exception as e:
        logger.warning("[InputAcceptance] capability resolution error: %s", e)
    return report


def check_input_acceptance(path: Path) -> InputAcceptanceReport:
    """Run full input acceptance pipeline and return structured report."""
    report = InputAcceptanceReport()

    # 1. Input probe
    probe_report = _build_input_probe(path)
    report.input = probe_report

    # Early exit if file not found
    if not probe_report.exists:
        report.decision = InputDecisionReport(
            accepted=False,
            outcome="reject",
            reason="FILE_NOT_FOUND",
            suggestion="Check the file path and retry.",
        )
        return report
    if not probe_report.readable:
        report.decision = InputDecisionReport(
            accepted=False,
            outcome="reject",
            reason="FILE_NOT_READABLE",
            suggestion="Check file permissions and retry.",
        )
        return report

    # 2. Capability probe
    cap_report = _build_capability_report(path, probe_report.mime_type)
    report.capability = cap_report

    # 3. Resource gate
    resource_report = _build_resource_gate(path, probe_report)
    report.resource_gate = resource_report

    if resource_report.status == "fail":
        report.decision = InputDecisionReport(
            accepted=False,
            outcome="reject",
            reason=resource_report.violations[0] if resource_report.violations else "RESOURCE_GATE_FAIL",
            suggestion="",
        )
        # Interpret violation for suggestion
        if "FILE_TOO_SMALL" in str(resource_report.violations):
            report.decision.suggestion = "The file is too small. Re-export with valid content."
        elif "FILE_TOO_LARGE" in str(resource_report.violations):
            report.decision.suggestion = "File exceeds maximum size. Split or reduce file size."
        return report

    # 4. Safety gate
    safety_report = _build_safety_gate(path, probe_report)
    report.safety_gate = safety_report

    if safety_report.status == "fail":
        error_code = safety_report.checks.get("error_code", "SAFETY_GATE_FAIL")
        suggestion = ""
        if error_code == "ENCRYPTED_PDF":
            suggestion = "Provide the password or decrypt the PDF and retry."
        elif error_code == "DAMAGED_PDF":
            suggestion = "Use a PDF repair tool to fix the file, or re-export from the source application."
        elif error_code == "INVALID_IMAGE":
            suggestion = "Re-export the file as PNG, JPEG, TIFF, or WebP and retry."
        elif error_code == "LOW_QUALITY_IMAGE":
            suggestion = "Increase image resolution, reduce noise, or use a clearer scan."
        elif error_code == "ARCHIVE_PASSWORD_PROTECTED":
            suggestion = "Remove password protection and re-upload."
        elif error_code == "ARCHIVE_RESOURCE_LIMIT":
            suggestion = "Split the archive into smaller parts."
        elif error_code == "ARCHIVE_UNSAFE_PATH":
            suggestion = "Remove dangerous members from the archive."
        report.decision = InputDecisionReport(
            accepted=False,
            outcome="reject",
            reason=error_code,
            suggestion=suggestion,
        )
        return report

    # 5. Capability decision
    if cap_report.support_status in ("unsupported", "planned"):
        report.decision = InputDecisionReport(
            accepted=False,
            outcome="reject",
            reason="UNSUPPORTED_FORMAT",
            suggestion="Convert to a supported format (PDF, PNG, JPEG, TIFF, DOCX, XLSX, PPTX).",
        )
        return report

    # All gates passed
    report.decision = InputDecisionReport(
        accepted=True,
        outcome="parse",
        reason="",
        suggestion="",
    )
    return report


def _detect_forgery(path: Path, transport: str) -> tuple[bool | None, tuple[str, ...]]:
    """Run transport-specific forgery checks during acceptance, once."""
    try:
        if transport == "pdf":
            from docmirror.framework.security.forgery_detector import detect_pdf_forgery

            forged, reasons = detect_pdf_forgery(path)
            return forged, tuple(reasons or ())
        if transport == "image":
            from docmirror.framework.security.forgery_detector import detect_image_forgery

            forged, reasons = detect_image_forgery(path)
            return forged, tuple(reasons or ())
    except Exception as exc:
        logger.warning("[InputAcceptance] forgery detection error: %s", exc)
    return None, ()


def accept_source(path: str | Path, *, declared_mime: str = "") -> AcceptedSource:
    """Return the sole immutable input accepted by ``ParserDispatcher``."""
    resolved = Path(path)
    report = check_input_acceptance(resolved)
    if not report.decision.accepted:
        raise InputRejectedError(report)

    from docmirror.configs.format.loader import load_format_registry

    capabilities, _, _ = load_format_registry()
    capability = capabilities.get(report.capability.id)
    if capability is None:
        report.decision = InputDecisionReport(
            accepted=False,
            outcome="reject",
            reason="UNSUPPORTED_FORMAT",
            suggestion="Convert to a supported format.",
        )
        raise InputRejectedError(report)
    is_forged, forgery_reasons = _detect_forgery(resolved, capability.transport)
    return AcceptedSource(
        path=resolved,
        original_name=resolved.name,
        size_bytes=report.input.size_bytes,
        detected_mime=report.input.mime_type,
        declared_mime=declared_mime,
        sha256=report.input.checksum,
        capability=capability,
        acceptance=report,
        is_forged=is_forged,
        forgery_reasons=forgery_reasons,
    )


__all__ = ["accept_source", "check_input_acceptance"]
