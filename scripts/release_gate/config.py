# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Release gate profiles and step registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ROOT_REL = "."  # cwd = repo root

StepKind = Literal["shell", "hygiene", "core_imports"]


@dataclass(frozen=True)
class GateStepDef:
    step_id: str
    title: str
    phase: str
    kind: StepKind
    profiles: frozenset[str]
    # shell: argv; hygiene/core_imports use kind-specific handlers
    argv: tuple[str, ...] = ()
    hygiene_checks: tuple[str, ...] | None = None  # None = all checks
    hygiene_strict: bool = False  # fail on hygiene errors
    hygiene_fail_on_warnings: bool = False
    optional: bool = False  # missing tool → skip instead of fail


PROFILES = ("quick", "standard", "full")

PROFILE_DESCRIPTIONS = {
    "quick": "Fast local check (~1–3 min): ruff + hygiene subset",
    "standard": "Pre-production gate (~8–20 min): CI parity without full regression",
    "full": "Release candidate (~30+ min): standard + tier tests + coverage upload",
}

STEPS: tuple[GateStepDef, ...] = (
    # ── Phase 1: Style ──
    GateStepDef(
        "ruff_format",
        "Ruff format (check)",
        "style",
        "shell",
        frozenset({"quick", "standard", "full"}),
        ("python3", "-m", "ruff", "format", "--check", "docmirror/"),
    ),
    GateStepDef(
        "ruff_lint",
        "Ruff lint (default rules)",
        "style",
        "shell",
        frozenset({"quick", "standard", "full"}),
        ("python3", "-m", "ruff", "check", "docmirror/"),
    ),
    # ── Phase 2: Hygiene ──
    GateStepDef(
        "hygiene_fast",
        "Code hygiene (F401/ARG/ERA/UP + commented blocks)",
        "hygiene",
        "hygiene",
        frozenset({"quick"}),
        hygiene_checks=("ruff_strict", "commented_blocks"),
    ),
    GateStepDef(
        "hygiene_full",
        "Code hygiene audit (strict, all checkers)",
        "hygiene",
        "hygiene",
        frozenset({"standard", "full"}),
        hygiene_checks=None,
        hygiene_strict=True,
    ),
    # ── Phase 3: Architecture & contracts (CI parity) ──
    GateStepDef(
        "validate_support_matrix",
        "Support Matrix registry",
        "contracts",
        "shell",
        frozenset({"standard", "full"}),
        ("python3", "scripts/validate/validate_support_matrix.py"),
    ),
    GateStepDef(
        "validate_real_world_fixture_catalog",
        "Real-world fixture catalog",
        "contracts",
        "shell",
        frozenset({"standard", "full"}),
        ("python3", "scripts/validate/validate_real_world_fixture_catalog.py"),
    ),
    GateStepDef(
        "validate_format_capabilities",
        "Format capability registry (FCR)",
        "contracts",
        "shell",
        frozenset({"standard", "full"}),
        ("python3", "scripts/validate/validate_format_capabilities.py"),
    ),
    GateStepDef(
        "validate_input_p0_matrix",
        "P0 input coverage matrix (IAC)",
        "contracts",
        "shell",
        frozenset({"standard", "full"}),
        ("python3", "scripts/validate/validate_input_p0_matrix.py"),
    ),
    GateStepDef(
        "validate_dti",
        "DTI classification maps",
        "contracts",
        "shell",
        frozenset({"standard", "full"}),
        ("python3", "scripts/validate/validate_dti.py"),
    ),
    GateStepDef(
        "validate_middleware_catalog",
        "Middleware + post-extract catalog (MEP)",
        "contracts",
        "shell",
        frozenset({"standard", "full"}),
        ("python3", "scripts/validate/validate_middleware_catalog.py"),
    ),
    GateStepDef(
        "validate_post_extract",
        "Post-extract catalog",
        "contracts",
        "shell",
        frozenset({"standard", "full"}),
        ("python3", "scripts/validate/validate_post_extract.py"),
    ),
    GateStepDef(
        "validate_test_manifest",
        "TQG test manifest",
        "contracts",
        "shell",
        frozenset({"standard", "full"}),
        ("python3", "scripts/validate/validate_test_manifest.py"),
    ),
    GateStepDef(
        "validate_core_cps_layout",
        "Core CPS layout (design 12)",
        "contracts",
        "shell",
        frozenset({"standard", "full"}),
        ("python3", "scripts/validate/validate_core_cps_layout.py"),
    ),
    GateStepDef(
        "validate_core_god_files",
        "Core god-file gate",
        "architecture",
        "shell",
        frozenset({"standard", "full"}),
        ("python3", "scripts/validate/validate_core_god_files.py"),
    ),
    GateStepDef(
        "gate_vnext_removed_refs",
        "PageProjection raw JSON reference gate",
        "architecture",
        "shell",
        frozenset({"standard", "full"}),
        ("python3", "scripts/validate/gate_vnext_removed_refs.py"),
    ),
    GateStepDef(
        "gate_vnext_mirror_volume",
        "PageProjection mirror volume gate",
        "architecture",
        "shell",
        frozenset({"standard", "full"}),
        ("python3", "scripts/validate/gate_vnext_mirror_volume.py"),
    ),
    GateStepDef(
        "validate_vnext_1_0_readiness",
        "vNext 1.0 readiness",
        "architecture",
        "shell",
        frozenset({"standard", "full"}),
        ("python3", "scripts/validate/validate_vnext_1_0_readiness.py"),
    ),
    GateStepDef(
        "audit_core_imports",
        "Core import graph (CPA §13)",
        "architecture",
        "core_imports",
        frozenset({"standard", "full"}),
    ),
    GateStepDef(
        "import_linter",
        "CCP import-linter contract",
        "architecture",
        "shell",
        frozenset({"standard", "full"}),
        ("lint-imports", "--config", ".importlinter"),
        optional=True,
    ),
    # ── Phase 4: Tests ──
    GateStepDef(
        "pytest_unit",
        "Unit tests",
        "tests",
        "shell",
        frozenset({"standard", "full"}),
        ("python3", "-m", "pytest", "tests/unit/", "-q", "--tb=line", "-p", "no:unraisableexception"),
    ),
    GateStepDef(
        "test_input_p0_matrix",
        "P0 input coverage contract tests (IAC)",
        "tests",
        "shell",
        frozenset({"standard", "full"}),
        (
            "python3",
            "-m",
            "pytest",
            "tests/contract/test_input_p0_matrix.py",
            "tests/contract/test_input_p0_office_smoke.py",
            "tests/contract/test_input_p0_web_email_archive_smoke.py",
            "-q",
            "--tb=line",
        ),
    ),
    GateStepDef(
        "pytest_tiers",
        "PR tier tests (smoke + contract + regression)",
        "tests",
        "shell",
        frozenset({"full"}),
        (
            "python3",
            "-m",
            "pytest",
            "tests/",
            "-q",
            "--tb=line",
            "-p",
            "no:unraisableexception",
            "--ignore=tests/unit",
            "-m",
            "tier_smoke or tier_contract or (tier_regression and not tier_slow)",
        ),
    ),
    GateStepDef(
        "pytest_coverage",
        "Coverage report (unit + tiers, no upload)",
        "tests",
        "shell",
        frozenset({"full"}),
        (
            "python3",
            "-m",
            "pytest",
            "tests/unit/",
            "tests/",
            "-q",
            "--tb=line",
            "-p",
            "no:unraisableexception",
            "--ignore=tests/unit",
            "-m",
            "tier_smoke or tier_contract or (tier_regression and not tier_slow)",
            "--cov=docmirror",
            "--cov-report=term-missing:skip-covered",
            "--cov-fail-under=0",
        ),
        optional=True,
    ),
)


def steps_for_profile(profile: str) -> list[GateStepDef]:
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile {profile!r}; choose from {PROFILES}")
    return [s for s in STEPS if profile in s.profiles]
