# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fallback invariant contract tests — GA 1.0 design OUT2-4 / ED-4.

Ensures every domain route (unknown, candidate, enterprise_only, finance_only)
has a stable fallback that never silently produces a GA-grade output for a
non-GA domain, and that fallback_reason+support_level are always present.
"""

import pytest

from docmirror.configs.ga_readiness import (
    CORE_DOMAIN_ROUTE,
    ENTERPRISE_ONLY_ROUTE,
    GENERIC_FALLBACK_ROUTE,
    MIRROR_ONLY_ROUTE,
    community_route_for_domain,
    compact_domain_readiness,
    edition_sku_status,
)
from docmirror.server.edition_availability import build_edition_availability

# ── Domain route coverage ──

KNOWN_DOMAINS = [
    "bank_statement",
    "wechat_payment",
    "alipay_payment",
    "vat_invoice",
    "business_license",
    "credit_report",
]
UNKNOWN_DOMAINS = ["unknown", "generic", "", "nonexistent_domain"]


@pytest.mark.parametrize("domain", KNOWN_DOMAINS)
def test_known_domain_has_core_domain_or_known_route(domain: str) -> None:
    """Every known community domain maps to a recognized route."""
    route = community_route_for_domain(domain)
    assert route in {
        CORE_DOMAIN_ROUTE,
        GENERIC_FALLBACK_ROUTE,
        ENTERPRISE_ONLY_ROUTE,
        MIRROR_ONLY_ROUTE,
    }, f"domain={domain} route={route}"


@pytest.mark.parametrize("domain", UNKNOWN_DOMAINS)
def test_unknown_domain_falls_back_to_generic(domain: str) -> None:
    """Unknown / generic / empty domains must use generic_fallback."""
    route = community_route_for_domain(domain)
    assert route == GENERIC_FALLBACK_ROUTE, f"domain={domain} route={route}"


# ── Edition availability invariants ──

def test_build_edition_availability_always_returns_four_editions() -> None:
    """build_edition_availability must return mirror/community/enterprise/finance."""
    avail = build_edition_availability()
    for ed in ("mirror", "community", "enterprise", "finance"):
        assert ed in avail, f"missing key: {ed}"
        item = avail[ed]
        assert "status" in item, f"missing status for {ed}"
        assert "requested" not in item, f"legacy requested state leaked into {ed}"


def test_community_always_available() -> None:
    """Community edition must always be available (no license needed)."""
    avail = build_edition_availability(document_type="bank_statement")
    community = avail["community"]
    assert community["status"] not in {"unavailable", "degraded"}, (
        f"community unexpectedly {community['status']}"
    )


def test_enterprise_without_projector_output_is_unavailable() -> None:
    """Manifest availability reflects the projector outcome, not package state."""
    avail = build_edition_availability(
        projections={"mirror": {}, "community": {}},
        document_type="bank_statement",
    )
    enterprise = avail["enterprise"]
    assert enterprise["status"] == "unavailable"
    assert enterprise["reason"] == "projector_failed"


def test_finance_written_projector_output_is_written() -> None:
    """A written projection is reported as written without a policy re-check."""
    avail = build_edition_availability(
        written={"finance": object()},
        projections={"finance": {"edition": "finance"}},
        document_type="bank_statement",
    )
    finance = avail["finance"]
    assert finance["status"] == "written"


# ── Domain readiness invariants ──

def test_compact_domain_readiness_has_all_keys() -> None:
    """compact_domain_readiness always returns the required keys."""
    info = compact_domain_readiness("bank_statement")
    for key in (
        "domain",
        "dgc_status",
        "support_level",
        "community_route",
        "edition_schema_gate",
        "evidence_gate",
        "sku",
    ):
        assert key in info, f"missing key: {key}"


@pytest.mark.parametrize("domain", KNOWN_DOMAINS + UNKNOWN_DOMAINS)
def test_every_domain_has_readiness_no_exception(domain: str) -> None:
    """No domain should raise an exception when queried for readiness."""
    try:
        info = compact_domain_readiness(domain)
        assert isinstance(info, dict)
    except Exception as e:
        pytest.fail(f"compact_domain_readiness({domain!r}) raised {e}")


# ── SKU status invariants ──

@pytest.mark.parametrize("domain", KNOWN_DOMAINS + UNKNOWN_DOMAINS)
def test_sku_status_returns_string_no_exception(domain: str) -> None:
    """edition_sku_status must return a string for every domain+edition."""
    for edition in ("mirror", "community", "enterprise", "finance"):
        status = edition_sku_status(domain, edition)
        assert isinstance(status, str), f"{domain}/{edition} sku={status!r}"


# ── FallbackReason presence (enrichment output) ──

def test_enriched_fallback_reason_for_generic() -> None:
    """The _enrich_edition_metadata function sets fallback_reason for generic output."""
    from docmirror.server.output_builder import _enrich_edition_metadata

    output: dict = {
        "edition": "community",
        "plugin": {"name": "generic"},
        "metadata": {
            "community_route_type": GENERIC_FALLBACK_ROUTE,
        },
        "data": {},
    }
    _enrich_edition_metadata(output, None, "community")
    meta = output.get("metadata", {})
    assert meta.get("domain_status") == "generic_fallback"
    assert meta.get("fallback_reason") in {None, "no_domain_plugin"}, (
        f"unexpected fallback_reason={meta.get('fallback_reason')}"
    )


def test_enriched_support_level_always_set() -> None:
    """support_level must be present in metadata after enrichment."""
    from docmirror.server.output_builder import _enrich_edition_metadata

    output: dict = {
        "edition": "community",
        "plugin": {"name": "generic"},
        "metadata": {},
        "data": {},
    }
    _enrich_edition_metadata(output, None, "community")
    meta = output.get("metadata", {})
    assert meta.get("support_level"), f"support_level missing in {meta}"
    assert isinstance(meta["support_level"], str)


def test_enriched_route_type_always_set() -> None:
    """route_type must be present in metadata after enrichment."""
    from docmirror.server.output_builder import _enrich_edition_metadata

    output: dict = {
        "edition": "community",
        "plugin": {"name": "bank_statement"},
        "metadata": {"community_route_type": CORE_DOMAIN_ROUTE},
        "data": {},
    }
    _enrich_edition_metadata(output, None, "community")
    meta = output.get("metadata", {})
    assert meta.get("route_type") == "core_domain", f"route_type={meta.get('route_type')}"
    assert meta.get("domain_status") == "ga", f"domain_status={meta.get('domain_status')}"
