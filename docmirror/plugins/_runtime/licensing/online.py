# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Online license manager — activation, verification, and caching.

Handles license key activation against DocMirror servers, periodic online
verification with offline grace period, machine fingerprint binding, and local
cache persistence for entitled feature lists.

Pipeline role: secondary channel after offline in ``entitlements.is_entitled``;
``plugins.__init__`` exposes ``license_manager`` for CLI activate/status commands.

Key exports: ``LicenseInfo``, ``LicenseManager``, ``license_manager``.

Dependencies: HTTP client for activation API, local cache file under user config dir.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class LicenseInfo:
    """License information data class."""

    def __init__(
        self,
        license_key: str,
        tier: str,
        plugins: list[str],
        expires_at: str,
        machine_id: str,
        issued_at: str,
    ):
        self.license_key = license_key
        self.tier = tier
        self.plugins = plugins
        self.expires_at = datetime.fromisoformat(expires_at)
        self.machine_id = machine_id
        self.issued_at = datetime.fromisoformat(issued_at)

    @property
    def is_expired(self) -> bool:
        """Check if license is expired."""
        return datetime.now() > self.expires_at

    @property
    def days_remaining(self) -> int:
        """Get days remaining until expiration."""
        delta = self.expires_at - datetime.now()
        return max(0, delta.days)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "license_key": self.license_key,
            "tier": self.tier,
            "plugins": self.plugins,
            "expires_at": self.expires_at.isoformat(),
            "machine_id": self.machine_id,
            "issued_at": self.issued_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LicenseInfo:
        """Create from dictionary."""
        return cls(
            license_key=data["license_key"],
            tier=data["tier"],
            plugins=data["plugins"],
            expires_at=data["expires_at"],
            machine_id=data["machine_id"],
            issued_at=data["issued_at"],
        )


class LicenseManager:
    """Manager for plugin license validation."""

    # API endpoints (can be overridden for testing)
    VERIFY_URL = os.getenv("DOCMIRROR_LICENSE_VERIFY_URL", "https://api.docmirror.com/v1/license/verify")
    ACTIVATE_URL = os.getenv("DOCMIRROR_LICENSE_ACTIVATE_URL", "https://api.docmirror.com/v1/license/activate")

    # Offline grace period (days)
    GRACE_PERIOD_DAYS = 7

    def __init__(self):
        """Initialize license manager."""
        self.license_key = os.getenv("DOCMIRROR_LICENSE")
        self.cache_dir = Path.home() / ".docmirror"
        self.cache_file = self.cache_dir / "license_cache.json"
        self._cached_license: LicenseInfo | None = None

        # Load cached license
        self._load_cache()

    def is_licensed(self, plugin_name: str) -> bool:
        """Check if a plugin is licensed.

        Args:
            plugin_name: Plugin name (e.g., "bank_statement_premium")

        Returns:
            True if plugin is licensed and valid
        """
        # Free community domains only apply to bare domain names, not *_premium features.
        from docmirror.plugins._runtime.licensing.tiers_loader import feature_suffix

        suffix = feature_suffix()
        if not plugin_name.endswith(suffix) and plugin_name in self._get_free_plugins():
            return True

        # Check if we have a license
        if not self.license_key:
            logger.debug(f"[LicenseManager] No license key for plugin '{plugin_name}'")
            return False

        # Validate license
        return self._validate_for_plugin(plugin_name)

    def activate(self, license_key: str) -> bool:
        """Activate a license key.

        Args:
            license_key: License key (e.g., "DOC-PRO-XXXX-XXXX-XXXX")

        Returns:
            True if activation successful
        """
        try:
            # Online activation
            result = self._activate_online(license_key)

            if result:
                # Save license key to env
                self.license_key = license_key

                # Update cache
                self._load_cache()

                logger.info("[LicenseManager] ✓ License activated successfully")
                return True
            else:
                logger.error("[LicenseManager] ✗ License activation failed")
                return False

        except Exception as e:
            logger.error(f"[LicenseManager] Activation error: {e}")
            return False

    def deactivate(self) -> bool:
        """Deactivate current license.

        Returns:
            True if deactivation successful
        """
        try:
            # Online deactivation (optional)
            if self.license_key:
                self._deactivate_online(self.license_key)

            # Clear local state
            self.license_key = None
            if self.cache_file.exists():
                self.cache_file.unlink()

            logger.info("[LicenseManager] ✓ License deactivated")
            return True

        except Exception as e:
            logger.error(f"[LicenseManager] Deactivation error: {e}")
            return False

    def get_license_info(self) -> dict[str, Any] | None:
        """Get current license information.

        Returns:
            License info dict or None
        """
        if self._cached_license is None:
            return None

        return {
            "tier": self._cached_license.tier,
            "plugins": self._cached_license.plugins,
            "expires_at": self._cached_license.expires_at.isoformat(),
            "days_remaining": self._cached_license.days_remaining,
            "is_expired": self._cached_license.is_expired,
        }

    def get_upgrade_message(self, plugin_name: str = "") -> str:
        """Get user-friendly upgrade message.

        Args:
            plugin_name: Optional plugin name for specific message

        Returns:
            Upgrade message string
        """
        if plugin_name:
            return (
                f"💡 插件 '{plugin_name}' 需要付费许可证。\n"
                f"   访问 https://docmirror.com/pricing 了解更多\n"
                f"   或使用基础版插件"
            )
        else:
            return (
                "💡 此功能需要付费许可证。\n"
                "   访问 https://docmirror.com/pricing 了解更多\n"
                "   社区版免费使用 17+ 基础插件"
            )

    def _validate_for_plugin(self, plugin_name: str) -> bool:
        """Validate license for a specific plugin.

        Args:
            plugin_name: Plugin name

        Returns:
            True if valid
        """
        # Try online validation first
        if self._validate_online():
            return self._check_plugin_access(plugin_name)

        # Fallback to offline grace period
        if self._validate_offline_grace():
            return self._check_plugin_access(plugin_name)

        logger.warning(f"[LicenseManager] License validation failed for '{plugin_name}'")
        return False

    def _validate_online(self) -> bool:
        """Validate license online.

        Returns:
            True if valid
        """
        try:
            import requests

            response = requests.post(
                self.VERIFY_URL,
                json={
                    "license_key": self.license_key,
                    "machine_id": self._get_machine_id(),
                },
                timeout=5,
            )

            if response.status_code == 200:
                # Update cache with new license info
                data = response.json()
                self._cached_license = LicenseInfo.from_dict(data)
                self._save_cache()
                return True
            else:
                logger.warning(f"[LicenseManager] Online validation failed: {response.status_code}")
                return False

        except ImportError:
            logger.warning("[LicenseManager] 'requests' library not installed")
            return False
        except Exception as e:
            logger.warning(f"[LicenseManager] Online validation error: {e}")
            return False

    def _validate_offline_grace(self) -> bool:
        """Validate license with offline grace period.

        Returns:
            True if within grace period
        """
        if self._cached_license is None:
            return False

        # Check if machine ID matches
        if self._cached_license.machine_id != self._get_machine_id():
            logger.warning("[LicenseManager] Machine ID mismatch")
            return False

        # Check grace period
        last_verify = self._get_last_verify_time()
        if last_verify is None:
            return False

        grace_end = last_verify + timedelta(days=self.GRACE_PERIOD_DAYS)
        if datetime.now() > grace_end:
            logger.warning(f"[LicenseManager] Offline grace period expired (last verify: {last_verify.isoformat()})")
            return False

        logger.debug(f"[LicenseManager] Using offline grace period (expires: {grace_end.isoformat()})")
        return True

    def _check_plugin_access(self, plugin_name: str) -> bool:
        """Check if license grants access to a plugin.

        Args:
            plugin_name: Plugin name

        Returns:
            True if access granted
        """
        if self._cached_license is None:
            return False

        # Check if expired
        if self._cached_license.is_expired:
            logger.warning("[LicenseManager] License expired")
            return False

        # Check if plugin is included
        if plugin_name in self._cached_license.plugins:
            return True

        # Check tier-based access
        tier_plugins = self._get_tier_plugins(self._cached_license.tier)
        if plugin_name in tier_plugins:
            return True

        logger.warning(f"[LicenseManager] Plugin '{plugin_name}' not included in license")
        return False

    def _activate_online(self, license_key: str) -> bool:
        """Activate license online.

        Args:
            license_key: License key

        Returns:
            True if successful
        """
        try:
            import requests

            response = requests.post(
                self.ACTIVATE_URL,
                json={
                    "license_key": license_key,
                    "machine_id": self._get_machine_id(),
                    "platform": platform.system(),
                    "version": "1.0.0",
                },
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                self._cached_license = LicenseInfo.from_dict(data)
                self._save_cache()
                return True
            else:
                error_msg = response.json().get("error", "Unknown error")
                logger.error(f"[LicenseManager] Activation failed: {error_msg}")
                return False

        except Exception as e:
            logger.error(f"[LicenseManager] Activation error: {e}")
            return False

    def _deactivate_online(self, license_key: str) -> None:
        """Deactivate license online.

        Args:
            license_key: License key
        """
        try:
            import requests

            response = requests.post(
                "https://api.docmirror.com/v1/license/deactivate",
                json={
                    "license_key": license_key,
                    "machine_id": self._get_machine_id(),
                },
                timeout=5,
            )

            if response.status_code == 200:
                logger.info("[LicenseManager] License deactivated online")
            else:
                logger.warning(f"[LicenseManager] Online deactivation failed: {response.status_code}")

        except Exception as e:
            logger.warning(f"[LicenseManager] Deactivation error: {e}")

    def _get_machine_id(self) -> str:
        """Get unique machine fingerprint.

        Returns:
            Machine ID hash
        """
        # Combine multiple hardware identifiers
        components = [
            str(uuid.getnode()),  # MAC address
            platform.machine(),  # Architecture
            platform.processor(),  # CPU
        ]

        # Create hash
        raw_id = "|".join(components)
        return hashlib.sha256(raw_id.encode()).hexdigest()

    def _get_free_plugins(self) -> list[str]:
        """Community premium domains (aligned with offline + tiers.yaml)."""
        from docmirror.plugins._runtime.licensing.tiers_loader import community_free_domains

        return community_free_domains()

    def _get_tier_plugins(self, tier: str) -> list[str]:
        """Get plugins included in a tier from tiers.yaml SSOT."""
        from docmirror.plugins._runtime.licensing.tiers_loader import tier_features

        return tier_features(tier)

    def _load_cache(self) -> None:
        """Load license from cache file."""
        if not self.cache_file.exists():
            return

        try:
            with open(self.cache_file) as f:
                data = json.load(f)

            self._cached_license = LicenseInfo.from_dict(data)
            logger.debug("[LicenseManager] License cache loaded")

        except Exception as e:
            logger.warning(f"[LicenseManager] Failed to load cache: {e}")

    def _save_cache(self) -> None:
        """Save license to cache file."""
        if self._cached_license is None:
            return

        try:
            # Ensure cache directory exists
            self.cache_dir.mkdir(parents=True, exist_ok=True)

            # Save license
            with open(self.cache_file, "w") as f:
                json.dump(self._cached_license.to_dict(), f, indent=2)

            # Save last verify time
            cache_data = {
                "last_verify": datetime.now().isoformat(),
            }
            cache_file = self.cache_dir / "license_verify_time.json"
            with open(cache_file, "w") as f:
                json.dump(cache_data, f, indent=2)

            logger.debug("[LicenseManager] License cache saved")

        except Exception as e:
            logger.error(f"[LicenseManager] Failed to save cache: {e}")

    def _get_last_verify_time(self) -> datetime | None:
        """Get last successful verification time.

        Returns:
            DateTime or None
        """
        cache_file = self.cache_dir / "license_verify_time.json"

        if not cache_file.exists():
            return None

        try:
            with open(cache_file) as f:
                data = json.load(f)

            return datetime.fromisoformat(data["last_verify"])

        except Exception as e:
            logger.warning(f"[LicenseManager] Failed to read verify time: {e}")
            return None


# Global singleton
license_manager = LicenseManager()

__all__ = ["LicenseManager", "LicenseInfo", "license_manager"]
