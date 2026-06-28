# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Offline license manager for air-gapped deployments.

Loads and validates signed ``.lic`` files with optional machine binding, long
validity periods, and post-expiry grace windows. Maintains an in-memory list of
license files and answers ``is_licensed(feature)`` queries.

Pipeline role: ``entitlements.is_entitled`` checks offline licenses first;
``snapshot.resolve_license_snapshot`` merges offline state for CLI display.

Key exports: ``LicenseFile``, ``OfflineLicenseManager``, ``offline_license_manager``.

Dependencies: stdlib crypto helpers (hash/base64), local filesystem for ``.lic`` paths.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import platform
import uuid
from datetime import datetime, timedelta
from json.decoder import JSONDecodeError
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class LicenseFile:
    """Represents a license file."""

    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.license_info = data.get("license_info", {})
        self.security = data.get("security", {})

        # Parse validity
        validity = self.license_info.get("validity", {})
        self.issued_at = datetime.fromisoformat(validity.get("issued_at"))
        self.expires_at = datetime.fromisoformat(validity.get("expires_at"))
        self.grace_period_days = validity.get("grace_period_days", 30)
        self.effective_expiry = self.expires_at + timedelta(days=self.grace_period_days)

        # Parse machine binding
        machine = self.license_info.get("machine_binding", {})
        self.machine_id = machine.get("machine_id")
        self.hostname = machine.get("hostname")
        self.allowed_machines = machine.get("allowed_machines", 1)

    @property
    def is_expired(self) -> bool:
        """Check if license is expired (excluding grace period)."""
        return datetime.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if license is still valid (including grace period)."""
        return datetime.now() <= self.effective_expiry

    @property
    def days_until_expiry(self) -> int:
        """Days until expiration (not including grace period)."""
        delta = self.expires_at - datetime.now()
        return delta.days

    @property
    def days_until_effective_expiry(self) -> int:
        """Days until effective expiry (including grace period)."""
        delta = self.effective_expiry - datetime.now()
        return delta.days

    @property
    def is_expiring_soon(self) -> bool:
        """Check if license is expiring within 90 days."""
        return 0 < self.days_until_expiry <= 90

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return self.data

    def get_features(self) -> list[str]:
        """Get licensed features."""
        return self.license_info.get("features", [])

    def get_tier(self) -> str:
        """Get license tier."""
        return self.license_info.get("tier", "free")

    def check_machine_binding(self) -> bool:
        """Check if current machine matches license binding."""
        if not self.machine_id:
            return True  # No binding

        current_machine_id = self._get_current_machine_id()
        return current_machine_id == self.machine_id

    def _get_current_machine_id(self) -> str:
        """Get current machine ID."""
        components = [
            str(uuid.getnode()),
            platform.machine(),
            platform.processor(),
        ]
        raw_id = "|".join(components)
        return hashlib.sha256(raw_id.encode()).hexdigest()


class OfflineLicenseManager:
    """Manager for offline license files."""

    _ONLINE_CACHE_TTL = timedelta(hours=24)

    def __init__(self):
        """Initialize offline license manager."""
        self.license_dir = Path.home() / ".docmirror" / "licenses"
        self.license_dir.mkdir(parents=True, exist_ok=True)

        self._licenses: list[LicenseFile] = []
        self._load_all_licenses()

    def load_license(self, license_path: str) -> bool:
        """Load a license file.

        Args:
            license_path: Path to .lic file

        Returns:
            True if loaded successfully
        """
        path = Path(license_path)

        if not path.exists():
            logger.error(f"[OfflineLicense] License file not found: {path}")
            return False

        try:
            # Read license file
            with open(path) as f:
                data = json.load(f)

            # Validate signature (in production, use RSA verification)
            if not self._verify_signature(data):
                logger.warning("[OfflineLicense] Invalid license signature — license file skipped")
                return False

            # Create license object
            license_file = LicenseFile(data)

            # Check machine binding
            if not license_file.check_machine_binding():
                logger.warning("[OfflineLicense] Machine ID mismatch — license skipped")
                return False

            # Professional tier is no longer supported — only Community/Enterprise/Finance/Ultimate
            if license_file.get_tier() == "professional":
                logger.warning("[OfflineLicense] Professional tier is no longer supported — license skipped")
                return False

            # Store license (replace same license_id if re-loaded)
            license_id = license_file.license_info.get("license_id")
            if license_id:
                self._licenses = [lic for lic in self._licenses if lic.license_info.get("license_id") != license_id]
            self._licenses.append(license_file)

            # Save to license directory
            dest_path = self.license_dir / f"{license_file.license_info['license_id']}.lic"
            with open(dest_path, "w") as f:
                json.dump(data, f, indent=2)

            logger.info(f"[OfflineLicense] ✓ License loaded: {license_file.license_info['license_id']}")
            logger.info(f"[OfflineLicense]   Tier: {license_file.get_tier()}")
            logger.info(f"[OfflineLicense]   Expires: {license_file.expires_at.isoformat()}")
            logger.info(f"[OfflineLicense]   Grace period: {license_file.grace_period_days} days")

            return True

        except Exception as e:
            logger.error(f"[OfflineLicense] Failed to load license: {e}")
            return False

    def is_licensed(self, plugin_name: str) -> bool:
        """Check if a plugin is licensed."""

        suffix = feature_suffix()

        # ── Step 1: Online verification (optional, non-blocking) ──
        # If DOCMIRROR_LICENSE_SERVER_URL is set, try server check first.
        # Falls back to offline if server unreachable.
        server_url = os.environ.get("DOCMIRROR_LICENSE_SERVER_URL")
        if server_url:
            online_result = self._online_check(server_url)
            if online_result is True:
                return True
            # online_result is False (server explicitly denied) or None (unreachable)
            # If server explicitly denied, do NOT fall through to offline
            if online_result is False:
                return False
            # online_result is None — server unreachable, fall through to offline

        # ── Step 2: Community free domains ──
        if not plugin_name.endswith(suffix) and plugin_name in self._get_free_plugins():
            return True

        check_name = plugin_name if plugin_name.endswith(suffix) else premium_feature(plugin_name)

        for license_file in self._licenses:
            if not license_file.is_valid:
                continue
            features = set(license_file.get_features())
            if "*" in features:
                return True
            if check_name in features:
                return True

        return False

    def get_license_info(self) -> dict[str, Any] | None:
        """Get license information.

        Returns:
            License info dict or None
        """
        if not self._licenses:
            return None

        # Return the most feature-rich license
        best_license = max(self._licenses, key=lambda lic: len(lic.get_features()))

        return {
            "license_id": best_license.license_info.get("license_id"),
            "tier": best_license.get_tier(),
            "type": best_license.license_info.get("type"),
            "issued_at": best_license.issued_at.isoformat(),
            "expires_at": best_license.expires_at.isoformat(),
            "grace_period_days": best_license.grace_period_days,
            "effective_expiry": best_license.effective_expiry.isoformat(),
            "days_until_expiry": best_license.days_until_expiry,
            "days_until_effective_expiry": best_license.days_until_effective_expiry,
            "is_expired": best_license.is_expired,
            "is_valid": best_license.is_valid,
            "is_expiring_soon": best_license.is_expiring_soon,
            "features": best_license.get_features(),
            "customer": best_license.license_info.get("customer", {}),
        }

    def list_licenses(self) -> list[dict[str, Any]]:
        """List all loaded licenses.

        Returns:
            List of license info dicts
        """
        licenses = []
        for lic in self._licenses:
            licenses.append(
                {
                    "license_id": lic.license_info.get("license_id"),
                    "tier": lic.get_tier(),
                    "expires_at": lic.expires_at.isoformat(),
                    "days_until_expiry": lic.days_until_expiry,
                    "is_valid": lic.is_valid,
                    "is_expiring_soon": lic.is_expiring_soon,
                    "features_count": len(lic.get_features()),
                }
            )
        return licenses

    def remove_license(self, license_id: str) -> bool:
        """Remove a license.

        Args:
            license_id: License ID to remove

        Returns:
            True if removed
        """
        # Remove from memory
        self._licenses = [lic for lic in self._licenses if lic.license_info.get("license_id") != license_id]

        # Remove from disk
        license_file = self.license_dir / f"{license_id}.lic"
        if license_file.exists():
            license_file.unlink()

        logger.info(f"[OfflineLicense] ✓ License removed: {license_id}")
        return True

    def check_expiring_licenses(self) -> list[dict[str, Any]]:
        """Check for licenses expiring soon.

        Returns:
            List of expiring license info
        """
        expiring = []
        for lic in self._licenses:
            if lic.is_expiring_soon:
                expiring.append(
                    {
                        "license_id": lic.license_info.get("license_id"),
                        "tier": lic.get_tier(),
                        "expires_at": lic.expires_at.isoformat(),
                        "days_until_expiry": lic.days_until_expiry,
                        "customer": lic.license_info.get("customer", {}),
                    }
                )

        return expiring

    def _load_all_licenses(self) -> None:
        """Load all licenses from license directory."""
        if not self.license_dir.exists():
            return

        for lic_file in self.license_dir.glob("*.lic"):
            try:
                self.load_license(str(lic_file))
            except Exception as e:
                logger.warning(f"[OfflineLicense] Failed to load {lic_file}: {e}")

    # Embedded RSA public key — issued by ValueMap Global.
    # Do not replace this key; licenses signed with a different key will fail verification.
    _PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAvVg39rHLs+iCwx7D7yCf
Y4+kFNWQYEBOq6OwyD8VVloyhCSSJlDgfv8/QzO5beyBkaPZXn6DApoGr49JehOj
8yOBCwlSqUUIe2mIU8MnStwsQ62MTP8TBmXcE8YSbY4P7/uwMgcTYr9sHu8jignu
ORITKoFw6T5Vu6U9/aQ4ehdloHW2D79taNHYtnP0Z7vOsp+832XTHDSq1wietRnY
CAHs5hoipKG7xdK5rxYEbQnZxvBkG/Qj66NPbvL9n3FsssAFw2yDnsTN23Z6glKo
/QIh1d14m9GHlz5/82yFSzKU+4k0bV2aLRiX7fu+qw3/0VO3vpLa0FikSqVSvras
/QIDAQAB
-----END PUBLIC KEY-----"""""

    def _verify_signature(self, data: dict[str, Any]) -> bool:
        """Verify license file signature using RSA-SHA256.

        Only RSA-SHA256 signatures signed with the embedded public key are accepted.
        The simplified checksum mode (for internal development) is not available
        in the open-source build.

        Args:
            data: License data

        Returns:
            True if signature is valid
        """
        security = data.get("security", {})
        signature = security.get("signature")
        if not signature:
            logger.error("[OfflineLicense] Missing signature in license file")
            return False

        # Reconstruct the exact string that was signed
        license_info = data.get("license_info", {})
        content_str = json.dumps(license_info, sort_keys=True)

        if not signature.startswith("RSA-SHA256:"):
            logger.error(f"[OfflineLicense] Unknown signature format: {signature.split(':')[0]}")
            return False

        try:
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError:
            logger.error("[OfflineLicense] cryptography package required to verify RSA signatures")
            return False

        signature_b64 = signature.split("RSA-SHA256:", 1)[1]
        try:
            sig_bytes = base64.b64decode(signature_b64)
        except Exception:
            logger.error("[OfflineLicense] Invalid base64 signature")
            return False

        # Use the embedded public key only — no external override
        try:
            public_key = serialization.load_pem_public_key(
                self._PUBLIC_KEY_PEM.encode(),
                backend=default_backend(),
            )
            public_key.verify(sig_bytes, content_str.encode(), padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception as e:
            logger.error(f"[OfflineLicense] Signature verification failed: {e}")
            return False

    def _get_free_plugins(self) -> list[str]:
        """Community premium domains that do not require enterprise license."""
        from docmirror.plugins._runtime.licensing.tiers_loader import community_free_domains

        return community_free_domains()


    def _online_check(self, server_url: str) -> bool | None:
        """Optional online license verification.

        Returns:
            True    — server confirmed validity
            False   — server explicitly denied
            None    — server unreachable, fall through to offline
        """
        cache_path = Path.home() / ".docmirror" / "license_online_cache.json"

        # ── Load cache ──
        if cache_path.exists():
            try:
                cache = json.loads(cache_path.read_text())
                cache_ts = cache.get("checked_at")
                if cache_ts:
                    checked = datetime.fromisoformat(cache_ts)
                    if datetime.now() - checked < self._ONLINE_CACHE_TTL:
                        return cache.get("result")
            except (JSONDecodeError, KeyError, ValueError):
                pass

        # ── Build request ──
        license_ids = [
            lic.license_info.get("license_id", "")
            for lic in self._licenses
        ]
        request = {
            "license_ids": license_ids,
            "machine_id": (self._licenses[0]._get_current_machine_id()
                           if self._licenses else ""),
            "client_version": self._get_own_version(),
        }

        # ── Call server (3s timeout, non-blocking) ──
        try:
            import requests as _req
            resp = _req.post(
                server_url.rstrip("/") + "/v1/license/check",
                json=request,
                timeout=3,
                headers={"User-Agent": f"DocMirror/{self._get_own_version()}"},
            )
        except Exception:
            logger.debug("[OnlineLicense] Server unreachable — falling back to offline")
            self._write_online_cache(cache_path, None)
            return None

        # ── Parse response ──
        if resp.status_code == 200:
            try:
                result = resp.json()
                valid = result.get("valid", False)
            except Exception:
                valid = False
            logger.info(f"[OnlineLicense] Server response: valid={valid}")
            self._write_online_cache(cache_path, valid)
            return valid
        elif resp.status_code in (401, 403):
            logger.warning("[OnlineLicense] Server denied access (401/403)")
            self._write_online_cache(cache_path, False)
            return False
        else:
            logger.warning(f"[OnlineLicense] Server returned {resp.status_code} — fallback")
            self._write_online_cache(cache_path, None)
            return None

    def _write_online_cache(self, path: Path, result: bool | None) -> None:
        try:
            path.write_text(json.dumps({"checked_at": datetime.now().isoformat(), "result": result}))
        except Exception:
            pass

    @staticmethod
    def _get_own_version() -> str:
        try:
            from docmirror import __version__
            return __version__
        except ImportError:
            return "unknown"


# Global singleton
offline_license_manager = OfflineLicenseManager()

__all__ = ["OfflineLicenseManager", "LicenseFile", "offline_license_manager"]