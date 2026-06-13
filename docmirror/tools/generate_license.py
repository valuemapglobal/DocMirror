# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
License Generator Tool (Vendor Side)
=====================================

This tool is used by DocMirror vendors to generate offline license files.

Usage:
    python -m docmirror.tools.generate_license \
        --customer "某某银行" \
        --contact "张三" \
        --email "zhangsan@bank.com" \
        --tier enterprise \
        --years 2 \
        --machines 5 \
        --output licenses/

Features:
    - Generate offline license files (.lic)
    - RSA signature encryption
    - Machine fingerprint binding (optional)
    - Batch generation support
    - License template management
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# Try to import cryptography, fallback to simplified mode
try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False
    print("⚠️  Warning: cryptography package not installed")
    print("   Install with: pip install cryptography")
    print("   Using simplified signature mode\n")


# Feature lists by tier
TIER_FEATURES = {
    "professional": [
        "bank_statement_premium",
        "audit_report_premium",
        "credit_report_premium",
    ],
    "enterprise": [
        "bank_statement_premium",
        "audit_report_premium",
        "credit_report_premium",
        "real_estate_premium",
        "contract_analysis_premium",
        "batch_processing",
        "priority_support",
    ],
    "ultimate": [
        "bank_statement_premium",
        "audit_report_premium",
        "credit_report_premium",
        "real_estate_premium",
        "contract_analysis_premium",
        "batch_processing",
        "priority_support",
        "custom_plugins",
        "white_label",
        "dedicated_support",
    ],
}


class LicenseGenerator:
    """Generate offline license files."""

    def __init__(self, private_key_path: str | None = None):
        """Initialize license generator.

        Args:
            private_key_path: Path to RSA private key file (PEM format)
        """
        self.private_key = None
        self.public_key_id = "key-2026-001"

        if private_key_path:
            self._load_private_key(private_key_path)
        elif HAS_CRYPTOGRAPHY:
            # Generate temporary key for testing
            print("⚠️  No private key provided, generating temporary key")
            self.private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend(),
            )

    def _load_private_key(self, key_path: str) -> None:
        """Load RSA private key from file."""
        if not HAS_CRYPTOGRAPHY:
            raise RuntimeError("cryptography package required for RSA signing")

        key_file = Path(key_path)
        if not key_file.exists():
            raise FileNotFoundError(f"Private key not found: {key_path}")

        with open(key_file, "rb") as f:
            self.private_key = serialization.load_pem_private_key(
                f.read(),
                password=None,
                backend=default_backend(),
            )

        print(f"✅ Loaded private key: {key_path}")

    def generate_license(
        self,
        customer: dict[str, str],
        tier: str = "professional",
        duration_years: int = 1,
        machine_id: str | None = None,
        hostname: str | None = None,
        allowed_machines: int = 1,
        custom_features: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a license file.

        Args:
            customer: Customer information dict
            tier: License tier (professional/enterprise/ultimate)
            duration_years: Validity period in years
            machine_id: Machine fingerprint (optional)
            hostname: Server hostname (optional)
            allowed_machines: Number of allowed machines
            custom_features: Custom feature list (overrides tier features)

        Returns:
            License data dict
        """
        # Validate tier
        if tier not in TIER_FEATURES:
            raise ValueError(f"Invalid tier: {tier}. Must be one of {list(TIER_FEATURES.keys())}")

        # Generate license ID
        now = datetime.now()
        license_id = f"LIC-{now.year}-{tier.upper()[:3]}-{hashlib.md5(str(now).encode()).hexdigest()[:8].upper()}"

        # Calculate validity
        issued_at = now
        expires_at = now + timedelta(days=365 * duration_years)
        grace_period_days = 30
        effective_expiry = expires_at + timedelta(days=grace_period_days)

        # Get features
        features = custom_features or TIER_FEATURES.get(tier, [])

        # Build license data
        license_data = {
            "license_file": f"docmirror-{tier}.lic",
            "version": "2.0",
            "license_info": {
                "license_id": license_id,
                "type": "subscription",
                "tier": tier,
                "billing_cycle": "yearly",
                "validity": {
                    "issued_at": issued_at.isoformat(),
                    "expires_at": expires_at.isoformat(),
                    "grace_period_days": grace_period_days,
                    "effective_expiry": effective_expiry.isoformat(),
                },
                "machine_binding": {
                    "machine_id": machine_id,
                    "hostname": hostname,
                    "allowed_machines": allowed_machines,
                },
                "features": features,
                "customer": customer,
            },
            "security": {
                "signature": "",  # Will be filled after signing
                "public_key_id": self.public_key_id,
                "checksum": "",
            },
        }

        # Calculate checksum
        content_str = json.dumps(license_data["license_info"], sort_keys=True)
        checksum = hashlib.sha256(content_str.encode()).hexdigest()
        license_data["security"]["checksum"] = f"sha256:{checksum}"

        # Sign license
        signature = self._sign_license(content_str)
        license_data["security"]["signature"] = signature

        return license_data

    def _sign_license(self, content: str) -> str:
        """Sign license content.

        Args:
            content: License content string

        Returns:
            Signature string
        """
        if self.private_key is None:
            # Simplified mode (no cryptography)
            signature_hash = hashlib.sha256(content.encode()).hexdigest()
            return f"simplified:{signature_hash}"

        # RSA signature
        signature = self.private_key.sign(
            content.encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

        # Encode to base64
        import base64

        signature_b64 = base64.b64encode(signature).decode()
        return f"RSA-SHA256:{signature_b64}"

    def save_license(self, license_data: dict[str, Any], output_path: str) -> str:
        """Save license to file.

        Args:
            license_data: License data dict
            output_path: Output directory or file path

        Returns:
            Path to saved license file
        """
        output = Path(output_path)

        # If directory, create filename
        if output.is_dir() or not output.suffix:
            output.mkdir(parents=True, exist_ok=True)
            license_id = license_data["license_info"]["license_id"]
            tier = license_data["license_info"]["tier"]
            filename = f"docmirror-{tier}-{license_id}.lic"
            output = output / filename

        # Save license
        with open(output, "w") as f:
            json.dump(license_data, f, indent=2, ensure_ascii=False)

        return str(output)

    def generate_batch_licenses(
        self,
        customers: list[dict[str, str]],
        tier: str = "enterprise",
        duration_years: int = 2,
        allowed_machines: int = 5,
        output_dir: str = "licenses",
    ) -> list[str]:
        """Generate multiple licenses in batch.

        Args:
            customers: List of customer info dicts
            tier: License tier
            duration_years: Validity period
            allowed_machines: Machines per license
            output_dir: Output directory

        Returns:
            List of generated license file paths
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        license_files = []
        for customer in customers:
            print(f"\n📝 Generating license for: {customer.get('company', 'Unknown')}")

            license_data = self.generate_license(
                customer=customer,
                tier=tier,
                duration_years=duration_years,
                allowed_machines=allowed_machines,
            )

            license_file = self.save_license(license_data, str(output_path))
            license_files.append(license_file)

            print(f"  ✅ License ID: {license_data['license_info']['license_id']}")
            print(f"  📁 File: {license_file}")

        return license_files


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate DocMirror offline license files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate single license
  python -m docmirror.tools.generate_license \\
      --customer "某某银行" \\
      --contact "张三" \\
      --email "zhangsan@bank.com" \\
      --tier enterprise \\
      --years 2 \\
      --machines 5

  # Generate with private key
  python -m docmirror.tools.generate_license \\
      --key /path/to/private.pem \\
      --customer "某某公司" \\
      --contact "李四" \\
      --email "lisi@company.com" \\
      --tier professional \\
      --years 1

  # Batch generation from JSON file
  python -m docmirror.tools.generate_license \\
      --batch customers.json \\
      --tier enterprise \\
      --years 2
        """,
    )

    # Customer info
    parser.add_argument("--customer", help="Customer company name")
    parser.add_argument("--contact", help="Contact person name")
    parser.add_argument("--email", help="Contact email")
    parser.add_argument("--phone", help="Contact phone")

    # License config
    parser.add_argument(
        "--tier",
        choices=["professional", "enterprise", "ultimate"],
        default="professional",
        help="License tier (default: professional)",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=1,
        help="License duration in years (default: 1)",
    )
    parser.add_argument(
        "--machines",
        type=int,
        default=1,
        help="Number of allowed machines (default: 1)",
    )
    parser.add_argument("--machine-id", help="Bind to specific machine ID")
    parser.add_argument("--hostname", help="Bind to specific hostname")

    # Security
    parser.add_argument("--key", help="Path to RSA private key file (PEM)")

    # Output
    parser.add_argument(
        "--output",
        default="licenses",
        help="Output directory (default: licenses)",
    )

    # Batch mode
    parser.add_argument(
        "--batch",
        help="Path to JSON file with customer list for batch generation",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.batch and not args.customer:
        parser.error("Either --customer or --batch is required")

    # Initialize generator
    try:
        generator = LicenseGenerator(private_key_path=args.key)
    except Exception as e:
        print(f"❌ Failed to initialize license generator: {e}")
        sys.exit(1)

    # Batch mode
    if args.batch:
        batch_file = Path(args.batch)
        if not batch_file.exists():
            print(f"❌ Batch file not found: {args.batch}")
            sys.exit(1)

        with open(batch_file) as f:
            customers = json.load(f)

        print(f"\n🚀 Batch generating {len(customers)} licenses...")
        print(f"📦 Tier: {args.tier}")
        print(f"⏱️  Duration: {args.years} years")
        print(f"💻 Machines per license: {args.machines}")

        license_files = generator.generate_batch_licenses(
            customers=customers,
            tier=args.tier,
            duration_years=args.years,
            allowed_machines=args.machines,
            output_dir=args.output,
        )

        print(f"\n✅ Generated {len(license_files)} licenses")
        print(f"📁 Output directory: {args.output}")
        return

    # Single license mode
    customer = {
        "company": args.customer,
        "contact": args.contact or "N/A",
        "email": args.email or "N/A",
        "phone": args.phone or "N/A",
    }

    print("\n🚀 Generating license...")
    print(f"👤 Customer: {customer['company']}")
    print(f"📦 Tier: {args.tier}")
    print(f"⏱️  Duration: {args.years} years")
    print(f"💻 Allowed machines: {args.machines}")

    license_data = generator.generate_license(
        customer=customer,
        tier=args.tier,
        duration_years=args.years,
        machine_id=args.machine_id,
        hostname=args.hostname,
        allowed_machines=args.machines,
    )

    license_file = generator.save_license(license_data, args.output)

    print(f"\n{'=' * 60}")
    print("✅ License generated successfully!")
    print(f"{'=' * 60}")
    print(f"📄 License ID:  {license_data['license_info']['license_id']}")
    print(f"📁 File:        {license_file}")
    print(f"📅 Issued:      {license_data['license_info']['validity']['issued_at']}")
    print(f"⏰ Expires:     {license_data['license_info']['validity']['expires_at']}")
    print(f"🎁 Grace Period: {license_data['license_info']['validity']['grace_period_days']} days")
    print(f"🔒 Features:    {len(license_data['license_info']['features'])}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
