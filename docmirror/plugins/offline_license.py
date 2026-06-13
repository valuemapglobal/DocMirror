# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Offline License Manager
=======================

Supports offline license validation for air-gapped environments.

Features:
- License file (.lic) loading and validation
- Offline verification with cryptographic signature
- Long validity period (1-3 years)
- Grace period after expiration (30 days)
- Machine binding (optional)
- Batch license management

Usage:
    from docmirror.plugins import offline_license_manager

    # Load license file
    offline_license_manager.load_license("/path/to/license.lic")

    # Check if plugin is licensed
    if offline_license_manager.is_licensed("bank_statement_premium"):
        print("✅ Licensed")

    # Get license info
    info = offline_license_manager.get_license_info()
    print(f"Expires: {info['expires_at']}")
    print(f"Grace period: {info['grace_period_days']} days")
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

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
                logger.error("[OfflineLicense] Invalid license signature")
                return False

            # Create license object
            license_file = LicenseFile(data)

            # Check machine binding
            if not license_file.check_machine_binding():
                logger.error("[OfflineLicense] Machine ID mismatch")
                return False

            # Store license
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
        """Check if a plugin is licensed.

        Args:
            plugin_name: Plugin name

        Returns:
            True if plugin is licensed and valid
        """
        # Check free plugins
        if plugin_name in self._get_free_plugins():
            return True

        # Find valid license that includes this plugin
        for license_file in self._licenses:
            # Check if license is still valid (including grace period)
            if not license_file.is_valid:
                continue

            # Check if plugin is included
            if plugin_name in license_file.get_features():
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

    def _verify_signature(self, data: dict[str, Any]) -> bool:
        """Verify license file signature using RSA-SHA256 or simplified checksum.

        Args:
            data: License data

        Returns:
            True if signature is valid
        """
        import os
        import base64
        import hashlib
        import json
        
        security = data.get("security", {})
        signature = security.get("signature")
        if not signature:
            logger.error("[OfflineLicense] Missing signature in license file")
            return False

        # Reconstruct the exact string that was signed
        license_info = data.get("license_info", {})
        content_str = json.dumps(license_info, sort_keys=True)

        if signature.startswith("simplified:"):
            expected_hash = hashlib.sha256(content_str.encode()).hexdigest()
            actual_hash = signature.split("simplified:", 1)[1]
            return expected_hash == actual_hash

        elif signature.startswith("RSA-SHA256:"):
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

            # Load public key
            public_key_pem = os.environ.get("DOCMIRROR_PUBLIC_KEY")
            if not public_key_pem:
                key_path = Path.home() / ".docmirror" / "public.pem"
                if key_path.exists():
                    public_key_pem = key_path.read_text()
                else:
                    logger.error(f"[OfflineLicense] Public key not found. Please set DOCMIRROR_PUBLIC_KEY or place public.pem in {key_path.parent}")
                    return False
            
            try:
                public_key = serialization.load_pem_public_key(
                    public_key_pem.encode() if isinstance(public_key_pem, str) else public_key_pem,
                    backend=default_backend()
                )
                public_key.verify(
                    sig_bytes,
                    content_str.encode(),
                    padding.PKCS1v15(),
                    hashes.SHA256()
                )
                return True
            except Exception as e:
                logger.error(f"[OfflineLicense] Signature verification failed: {e}")
                return False
        else:
            logger.error(f"[OfflineLicense] Unknown signature format: {signature.split(':')[0]}")
            return False

    def _get_free_plugins(self) -> list[str]:
        """Get list of free (community edition) plugins.

        These plugin domains are always free in the community edition.
        Enterprise plugins require a valid license file.
        """
        # Community edition plugins (18 baseline domains)
        return [
            # P0 — 普通人最高频
            "bank_statement",
            "wechat_payment",
            "alipay_payment",
            "id_card",
            "passport",
            "business_license",
            "vat_invoice",
            "credit_report",
            "loan_contract",
            # P1 — 中频实用
            "real_estate_certificate",
            "mortgage_contract",
            "insurance_policy",
            "tax_certificate",
            "social_security_proof",
            "payroll_slip",
            # P2 — 可用
            "drivers_license",
            "household_registration",
            "social_security_card",
        ]


# Global singleton
offline_license_manager = OfflineLicenseManager()

__all__ = ["OfflineLicenseManager", "LicenseFile", "offline_license_manager"]
