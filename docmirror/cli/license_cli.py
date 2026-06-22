# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Top-level ``docmirror license`` CLI group.

Provides a standalone Click group (not nested under ``plugins``) so that
``docmirror license show``, ``docmirror license activate KEY``, etc. work
as first-class commands. The same group can also be attached under
``docmirror plugins`` for backward compatibility.

Commands::

    docmirror license show
    docmirror license activate <key>
    docmirror license deactivate
    docmirror license load <license-file>
    docmirror license check-expiring
"""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


@click.group()
def license_group():
    """License management commands."""
    pass


@license_group.command()
def show():
    """Show current license information (offline + online)."""
    from docmirror.plugins.licensing.snapshot import resolve_license_snapshot

    snapshot = resolve_license_snapshot()
    offline = snapshot.get("offline")
    online = snapshot.get("online")
    channel = snapshot.get("active_channel")

    if not offline and not online:
        console.print(
            Panel(
                "[yellow]No active license[/yellow]\n\n"
                "Load offline: [cyan]docmirror license load company.lic[/cyan]\n"
                "Or activate online: [cyan]docmirror license activate KEY[/cyan]\n\n"
                "Visit [cyan]https://docmirror.com/pricing[/cyan] to purchase.",
                title="License Status",
                border_style="yellow",
            )
        )
        return

    table = Table(title="License Snapshot", border_style="green")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Active Channel", channel or "none")
    table.add_row("Lifecycle", str(snapshot.get("lifecycle_state", "missing")))
    if snapshot.get("lifecycle_days_remaining") is not None:
        table.add_row("Days Remaining", str(snapshot.get("lifecycle_days_remaining", "")))
    if snapshot.get("lifecycle_state") == "expiring_soon":
        table.add_row("Expiring Soon", "⚠️ Yes")
    elif snapshot.get("lifecycle_state") == "grace_period":
        table.add_row("Grace Period", "⚠️ Active")
    if offline:
        table.add_row("Offline Tier", str(offline.get("tier", "N/A")).upper())
        table.add_row("Offline Valid", "✅" if offline.get("is_valid") else "❌")
        table.add_row("Offline Expires", str(offline.get("expires_at", "N/A")))
        table.add_row("Grace (days)", str(offline.get("grace_period_days", "N/A")))
        table.add_row("Effective Expiry", str(offline.get("effective_expiry", "N/A")))
        sample = snapshot.get("entitled_features_sample") or []
        table.add_row("Features (sample)", ", ".join(sample[:8]) + ("…" if len(sample) > 8 else ""))
    if online:
        table.add_row("Online Tier", str(online.get("tier", "N/A")).upper())
        table.add_row("Online Status", "✅ Active" if not online.get("is_expired") else "❌ Expired")
        table.add_row("Online Expires", str(online.get("expires_at", "N/A")))
        table.add_row("Online Days Left", str(online.get("days_remaining", "N/A")))

    console.print(table)

    offline_list = snapshot.get("offline_licenses") or []
    if len(offline_list) > 1:
        console.print(f"[dim]Loaded offline licenses: {len(offline_list)}[/dim]")


@license_group.command("check-expiring")
def check_expiring():
    """List licenses expiring within the configured threshold (default 90 days)."""
    from docmirror.plugins.licensing.offline import offline_license_manager
    from docmirror.plugins.licensing.online import license_manager
    from docmirror.plugins.licensing.tiers_loader import load_tiers

    threshold = int((load_tiers().get("lifecycle") or {}).get("expiring_soon_days") or 90)
    rows: list[tuple[str, str, str, str]] = []

    for item in offline_license_manager.check_expiring_licenses():
        rows.append(
            (
                "offline",
                str(item.get("license_id", "")),
                str(item.get("tier", "")),
                str(item.get("days_until_expiry", "")),
            )
        )

    online = license_manager.get_license_info()
    if online and not online.get("is_expired"):
        days = int(online.get("days_remaining") or 0)
        if 0 < days <= threshold:
            rows.append(("online", "cached", str(online.get("tier", "")), str(days)))

    if not rows:
        console.print(
            Panel(
                f"[green]No licenses expiring within {threshold} days.[/green]",
                title="License Expiry Check",
                border_style="green",
            )
        )
        return

    table = Table(title=f"Licenses Expiring Within {threshold} Days", border_style="yellow")
    table.add_column("Channel", style="cyan")
    table.add_column("License ID", style="white")
    table.add_column("Tier", style="white")
    table.add_column("Days Left", style="yellow")
    for row in rows:
        table.add_row(*row)
    console.print(table)


@license_group.command()
@click.argument("key")
def activate(key: str):
    """Activate a license key."""
    from docmirror.plugins import license_manager

    console.print("[cyan]Activating license...[/cyan]")

    success = license_manager.activate(key)

    if success:
        info = license_manager.get_license_info()
        console.print(
            Panel(
                f"[bold green]✅ License activated successfully![/bold green]\n\n"
                f"[b]Tier:[/b] {info['tier'].upper()}\n"
                f"[b]Expires:[/b] {info['expires_at']}\n"
                f"[b]Days remaining:[/b] {info['days_remaining']}\n"
                f"[b]Plugins:[/b] {', '.join(info['plugins'])}",
                title="License Activated",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                "[bold red]❌ License activation failed[/bold red]\n\n"
                "Please check:\n"
                "  • License key is correct\n"
                "  • Internet connection\n"
                "  • License not already activated on another machine\n\n"
                "Contact [cyan]support@docmirror.com[/cyan] for help.",
                title="Activation Failed",
                border_style="red",
            )
        )
        sys.exit(1)


@license_group.command()
@click.argument("license_file", type=click.Path(exists=True))
def load(license_file: str):
    """Load offline license file (.lic)."""
    from docmirror.plugins.licensing.offline import offline_license_manager

    console.print(f"[cyan]Loading offline license: {license_file}[/cyan]")

    success = offline_license_manager.load_license(license_file)

    if success:
        info = offline_license_manager.get_license_info()
        console.print(
            Panel(
                f"[bold green]✅ Offline license loaded successfully![/bold green]\n\n"
                f"[b]License ID:[/b] {info['license_id']}\n"
                f"[b]Tier:[/b] {info['tier'].upper()}\n"
                f"[b]Issued:[/b] {info['issued_at']}\n"
                f"[b]Expires:[/b] {info['expires_at']}\n"
                f"[b]Grace Period:[/b] {info['grace_period_days']} days\n"
                f"[b]Effective Expiry:[/b] {info['effective_expiry']}\n"
                f"[b]Days Remaining:[/b] {info['days_until_effective_expiry']}\n\n"
                f"[dim]💡 This license works offline, no need to renew regularly[/dim]",
                title="Offline License Loaded",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                "[bold red]❌ Failed to load offline license[/bold red]\n\n"
                "Please check:\n"
                "  • License file is valid\n"
                "  • License file is not corrupted\n"
                "  • Machine ID matches (if bound)\n\n"
                "Contact [cyan]support@docmirror.com[/cyan] for help.",
                title="Load Failed",
                border_style="red",
            )
        )
        sys.exit(1)


@license_group.command()
def deactivate():
    """Deactivate current license."""
    from docmirror.plugins import license_manager

    if not license_manager.get_license_info():
        console.print("[yellow]No active license to deactivate[/yellow]")
        return

    console.print("[cyan]Deactivating license...[/cyan]")
    success = license_manager.deactivate()

    if success:
        console.print("[bold green]✅[/bold green] License deactivated successfully")
        console.print("[dim]   You can activate it again on another machine[/dim]")
    else:
        console.print("[bold red]❌[/bold red] Failed to deactivate license")
        sys.exit(1)


__all__ = ["license_group"]
