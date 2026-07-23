# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Plugin management CLI for DocMirror premium and community extensions.

Provides Click commands to list, enable, disable, inspect, and search plugins
from the local registry, plus license activation and entitlement diagnostics.
Only post-seal edition projectors appear here. Core canonical domain
capabilities are not runtime plugins and cannot be enabled or disabled.

Commands::

    docmirror plugins
    docmirror plugins ls
    docmirror plugins enable <name>
    docmirror plugins disable <name>
    docmirror plugins info <name>
    docmirror plugins search <keyword>
    docmirror license
    docmirror license activate <key>
    docmirror license deactivate
    docmirror plugins stats
"""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# Import managers
from docmirror.plugins import license_manager, plugin_manager
from docmirror.plugins._runtime.licensing.offline import offline_license_manager


@click.group(invoke_without_command=True)
@click.pass_context
def plugins(ctx: click.Context):
    """Plugin management commands; list installed plugins when omitted."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(list_plugins)


@plugins.command("ls")
@click.option("--enabled", is_flag=True, help="Show only enabled plugins")
@click.option("--disabled", is_flag=True, help="Show only disabled plugins")
@click.option("--all", "show_all", is_flag=True, help="Include all registered enterprise/finance domains")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table", help="Output format")
def list_plugins(enabled: bool, disabled: bool, show_all: bool, fmt: str):
    """List installed post-seal projector plugins."""
    all_plugins = plugin_manager.list_all()

    # Filter
    if enabled:
        all_plugins = [p for p in all_plugins if p["enabled"]]
    elif disabled:
        all_plugins = [p for p in all_plugins if not p["enabled"]]

    if fmt == "json":
        import json

        click.echo(json.dumps(all_plugins, indent=2, ensure_ascii=False))
        return

    # Table format
    table = Table(title=f"Plugins ({len(all_plugins)} total)")
    table.add_column("Status", style="cyan", width=8)
    table.add_column("Name", style="green", width=30)
    table.add_column("Display Name", style="white", width=35)
    table.add_column("Type", style="yellow", width=10)

    for p in all_plugins:
        status = "✅" if p["enabled"] else "❌"
        table.add_row(
            status,
            p["name"],
            p["display_name"],
            p.get("type", "builtin"),
        )

    console.print(table)

    # Summary
    enabled_count = sum(1 for p in all_plugins if p["enabled"])
    disabled_count = len(all_plugins) - enabled_count
    console.print(f"\n[dim]Enabled: {enabled_count} | Disabled: {disabled_count}[/dim]")


@plugins.command()
@click.argument("name")
def enable(name: str):
    """Enable a plugin."""
    try:
        success = plugin_manager.enable(name)
        if success:
            console.print(f"[bold green]✅[/bold green] Plugin '[green]{name}[/green]' enabled")
            console.print("[dim]   The plugin will be loaded on next run[/dim]")
        else:
            console.print(f"[bold red]❌[/bold red] Failed to enable plugin '{name}'")
            sys.exit(1)
    except ValueError as e:
        console.print(f"[bold red]❌[/bold red] {str(e)}")
        sys.exit(1)


@plugins.command()
@click.argument("name")
def disable(name: str):
    """Disable a plugin."""
    try:
        success = plugin_manager.disable(name)
        if success:
            console.print(f"[bold yellow]⚠️[/bold yellow] Plugin '[yellow]{name}[/yellow]' disabled")
            console.print("[dim]   The plugin will not be loaded on next run[/dim]")
        else:
            console.print(f"[bold red]❌[/bold red] Failed to disable plugin '{name}'")
            sys.exit(1)
    except ValueError as e:
        console.print(f"[bold red]❌[/bold red] {str(e)}")
        sys.exit(1)


@plugins.command()
@click.argument("name")
def info(name: str):
    """Show plugin details."""
    try:
        status = plugin_manager.status(name)

        # Plugin info panel
        info_text = f"""
[b]Name:[/b]        {status["name"]}
[b]Display Name:[/b] {status["display_name"]}
[b]Status:[/b]       {"✅ Enabled" if status["enabled"] else "❌ Disabled"}
[b]Type:[/b]         {status.get("type", "builtin")}
[b]Version:[/b]      {status.get("version", "unknown")}
"""

        console.print(Panel(info_text.strip(), title=f"Plugin: {name}", border_style="cyan"))

        # Check license if premium
        if "premium" in name:
            console.print()
            licensed = license_manager.is_licensed(name)
            if licensed:
                console.print("[bold green]✅[/bold green] License: [green]Active[/green]")
                license_info = license_manager.get_license_info()
                if license_info:
                    console.print(f"[dim]   Tier: {license_info['tier']}[/dim]")
                    console.print(f"[dim]   Expires: {license_info['expires_at']}[/dim]")
                    console.print(f"[dim]   Days remaining: {license_info['days_remaining']}[/dim]")
            else:
                console.print("[bold red]❌[/bold red] License: [red]Not activated[/red]")
                console.print(license_manager.get_upgrade_message(name))

    except ValueError as e:
        console.print(f"[bold red]❌[/bold red] {str(e)}")
        sys.exit(1)


@plugins.command()
@click.argument("keyword")
@click.option("--all", "show_all", is_flag=True, help="Search all registered domains (not just community 6+1)")
def search(keyword: str, show_all: bool):
    """Search plugins by keyword."""
    all_plugins = plugin_manager.list_all() if show_all else plugin_manager.list_community()

    # Search in name and display_name
    results = [
        p for p in all_plugins if keyword.lower() in p["name"].lower() or keyword.lower() in p["display_name"].lower()
    ]

    if not results:
        console.print(f"[yellow]No plugins found matching '[yellow bold]{keyword}[/yellow bold]'[/yellow]")
        return

    table = Table(title=f"Search results for '{keyword}' ({len(results)} found)")
    table.add_column("Status", style="cyan", width=8)
    table.add_column("Name", style="green", width=30)
    table.add_column("Display Name", style="white")

    for p in results:
        status = "✅" if p["enabled"] else "❌"
        table.add_row(status, p["name"], p["display_name"])

    console.print(table)


@click.group("license", invoke_without_command=True)
@click.pass_context
def license(ctx: click.Context):
    """License management commands; show the active license when omitted."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(show)


@license.command()
def show():
    """Show current license information (offline + online)."""
    from docmirror.plugins._runtime.licensing.snapshot import resolve_license_snapshot

    snapshot = resolve_license_snapshot()
    offline = snapshot.get("offline")
    online = snapshot.get("online")
    channel = snapshot.get("active_channel")

    if not offline and not online:
        console.print(
            Panel(
                "[yellow]No active license[/yellow]\n\n"
                "Load offline: [cyan]docmirror license load company.lic[/cyan]\n"
                "Online activation requires an operator-configured endpoint.\n\n"
                "License guidance: [cyan]https://valuemapglobal.github.io/DocMirror/[/cyan]",
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
        cust = offline.get("customer", {})
        if isinstance(cust, dict):
            for ckey in ("company", "contact", "name"):
                cval = cust.get(ckey)
                if cval:
                    table.add_row(f"Customer {ckey.title()}", str(cval))
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


@license.command("check-expiring")
def check_expiring():
    """List licenses expiring within the configured threshold (default 90 days)."""
    from docmirror.plugins._runtime.licensing.offline import offline_license_manager
    from docmirror.plugins._runtime.licensing.online import license_manager
    from docmirror.plugins._runtime.licensing.tiers_loader import load_tiers

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


@license.command()
@click.argument("key")
def activate(key: str):
    """Activate a license key."""
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
                "  • DOCMIRROR_LICENSE_ACTIVATE_URL is configured\n"
                "  • License not already activated on another machine\n\n"
                "Open an issue: [cyan]https://github.com/valuemapglobal/DocMirror/issues[/cyan]",
                title="Activation Failed",
                border_style="red",
            )
        )
        sys.exit(1)


@license.command()
@click.argument("license_file", type=click.Path(exists=True))
def load(license_file: str):
    """Load offline license file (.lic)."""
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
                "Open an issue: [cyan]https://github.com/valuemapglobal/DocMirror/issues[/cyan]",
                title="Load Failed",
                border_style="red",
            )
        )
        sys.exit(1)


@license.command()
def deactivate():
    """Deactivate current license."""
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


@plugins.command()
@click.option("--all", "show_all", is_flag=True, help="Include all registered enterprise/finance domains")
def stats(show_all: bool):
    """Show plugin statistics."""
    all_plugins = plugin_manager.list_all() if show_all else plugin_manager.list_community()

    # Count by status
    enabled_count = sum(1 for p in all_plugins if p["enabled"])
    disabled_count = len(all_plugins) - enabled_count

    # Count by type
    builtin_count = sum(1 for p in all_plugins if p.get("type") == "builtin")
    premium_count = sum(1 for p in all_plugins if "premium" in p["name"])

    # License status
    license_info = license_manager.get_license_info()
    license_status = "Active" if license_info else "Not activated"
    license_tier = license_info["tier"].upper() if license_info else "N/A"

    # Stats panel
    stats_text = f"""
[b]Total Plugins:[/b]      {len(all_plugins)}
[b]Enabled:[/b]             {enabled_count}
[b]Disabled:[/b]            {disabled_count}

[b]Built-in:[/b]            {builtin_count}
[b]Premium:[/b]             {premium_count}

[b]License Status:[/b]      {license_status}
[b]License Tier:[/b]        {license_tier}
"""

    console.print(Panel(stats_text.strip(), title="Plugin Statistics", border_style="cyan"))

    # License details if active
    if license_info:
        console.print()
        table = Table(border_style="green")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Tier", license_info["tier"].upper())
        table.add_row("Expires", license_info["expires_at"])
        table.add_row("Days Remaining", str(license_info["days_remaining"]))
        table.add_row("Plugins", ", ".join(license_info["plugins"]))

        console.print(table)


# generate_demo command removed in v1.1
# License signing requires RSA private key — not available in open-source build.
# Use offline .lic files supplied directly by an authorized operator.

# Export for integration
__all__ = ["license", "plugins"]
