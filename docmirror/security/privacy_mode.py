# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Privacy Mode Resolver — determines the active privacy mode for each parse.

Resolves privacy mode from (in priority order):
  1. Environment variable DOCMIRROR_PRIVACY_MODE
  2. Privacy policy YAML (docmirror/configs/yaml/privacy_policy.yaml)
  3. Hardcoded default: local

Supported modes:
  - local: No network, no external OCR/VLM, no online license during parse.
  - egress_opt_in: Network allowed, but requires provider allowlist + consent.
  - offline_enterprise: No network, offline license only.
  - debug_internal: Raw debug artifacts allowed, local-only, not for public release.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import yaml

_PRIVACY_POLICY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "configs",
    "yaml",
    "privacy_policy.yaml",
)

DEFAULT_PRIVACY_MODE = "local"


class PrivacyMode(Enum):
    LOCAL = "local"
    EGRESS_OPT_IN = "egress_opt_in"
    OFFLINE_ENTERPRISE = "offline_enterprise"
    DEBUG_INTERNAL = "debug_internal"


@dataclass
class PrivacyPolicy:
    """Resolved privacy policy for the current process / task."""

    mode: str = DEFAULT_PRIVACY_MODE
    allow_network: bool = False
    allow_external_ocr: bool = False
    allow_vlm: bool = False
    allow_online_license_verify_during_parse: bool = False
    require_provider_allowlist: bool = True
    require_consent: bool = False
    require_egress_audit: bool = False
    support_bundle_profile: str = "redacted"
    log_profile: str = "minimal"
    provider_allowlist: dict[str, list[str]] = field(default_factory=dict)

    @property
    def is_local(self) -> bool:
        return self.mode == "local"

    @property
    def is_enterprise(self) -> bool:
        return self.mode == "offline_enterprise"

    @property
    def is_egress_opt_in(self) -> bool:
        return self.mode == "egress_opt_in"


def _load_privacy_policy_yaml() -> dict[str, Any]:
    """Load the privacy policy YAML file."""
    try:
        with open(_PRIVACY_POLICY_PATH) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def resolve_privacy_policy() -> PrivacyPolicy:
    """Resolve the active privacy policy from environment and YAML config."""

    yaml_data = _load_privacy_policy_yaml()

    # Determine mode: env var > yaml default > hardcoded default
    env_mode = os.environ.get("DOCMIRROR_PRIVACY_MODE")
    if env_mode:
        mode = env_mode.strip().lower()
    else:
        mode = yaml_data.get("default_mode", DEFAULT_PRIVACY_MODE)

    # Load mode-specific settings from YAML
    modes = yaml_data.get("modes", {})
    mode_config = modes.get(mode, modes.get("local", {}))

    # Network override via env
    env_network = os.environ.get("DOCMIRROR_ALLOW_NETWORK")
    if env_network is not None:
        allow_network = env_network.strip().lower() in ("1", "true", "yes")
    else:
        allow_network = mode_config.get("allow_network", False)

    policy = PrivacyPolicy(
        mode=mode,
        allow_network=allow_network,
        allow_external_ocr=mode_config.get("allow_external_ocr", False),
        allow_vlm=mode_config.get("allow_vlm", False),
        allow_online_license_verify_during_parse=mode_config.get("allow_online_license_verify_during_parse", False),
        require_provider_allowlist=mode_config.get("require_provider_allowlist", True),
        require_consent=mode_config.get("require_consent", False),
        require_egress_audit=mode_config.get("require_egress_audit", False),
        support_bundle_profile=mode_config.get("support_bundle_profile", "redacted"),
        log_profile=mode_config.get("log_profile", "minimal"),
        provider_allowlist=yaml_data.get("provider_allowlist", {}),
    )

    return policy


def is_provider_allowed(provider: str, provider_type: str, policy: PrivacyPolicy) -> bool:
    """Check if a specific provider is in the allowlist for the given type."""
    if not policy.require_provider_allowlist:
        return True
    allowlist = policy.provider_allowlist.get(provider_type, [])
    return provider in allowlist
