# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Plugin Management CLI
=====================

Command-line interface for managing DocMirror plugins.

Commands:
  - docmirror plugins list          # List all plugins
  - docmirror plugins enable <name> # Enable a plugin
  - docmirror plugins disable <name> # Disable a plugin
  - docmirror plugins info <name>   # Show plugin details
  - docmirror plugins search <kw>   # Search plugins
  - docmirror plugins license show  # Show license info
  - docmirror plugins license activate <key> # Activate license
  - docmirror plugins license deactivate # Deactivate license
  - docmirror plugins stats         # Show statistics

Usage:
    docmirror plugins list
    docmirror plugins enable id_card
    docmirror plugins disable passport
    docmirror plugins info bank_statement
    docmirror plugins license activate DOC-PRO-XXXX-XXXX
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
from docmirror.plugins.offline_license import offline_license_manager


@click.group()
def plugins():
    """Plugin management commands."""
    pass


@plugins.command()
@click.option("--enabled", is_flag=True, help="Show only enabled plugins")
@click.option("--disabled", is_flag=True, help="Show only disabled plugins")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table", help="Output format")
def list(enabled: bool, disabled: bool, fmt: str):
    """List all plugins."""
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
def search(keyword: str):
    """Search plugins by keyword."""
    all_plugins = plugin_manager.list_all()

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


@plugins.group()
def license():
    """License management commands."""
    pass


@license.command()
def show():
    """Show current license information."""
    info = license_manager.get_license_info()

    if info is None:
        console.print(
            Panel(
                "[yellow]No active license[/yellow]\n\n"
                "Visit [cyan]https://docmirror.com/pricing[/cyan] to purchase a license.",
                title="License Status",
                border_style="yellow",
            )
        )
        return

    # License info table
    table = Table(title="License Information", border_style="green")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Tier", info["tier"].upper())
    table.add_row("Status", "✅ Active" if not info["is_expired"] else "❌ Expired")
    table.add_row("Expires At", info["expires_at"])
    table.add_row("Days Remaining", str(info["days_remaining"]))
    table.add_row("Plugins", ", ".join(info["plugins"]))

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
                "  • Internet connection\n"
                "  • License not already activated on another machine\n\n"
                "Contact [cyan]support@docmirror.com[/cyan] for help.",
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
                "Contact [cyan]support@docmirror.com[/cyan] for help.",
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
def stats():
    """Show plugin statistics."""
    all_plugins = plugin_manager.list_all()

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


@license.command()
def generate_demo():
    """Generate a demo license file for development/testing."""
    import json
    import hashlib
    import uuid
    from datetime import datetime, timedelta
    from pathlib import Path

    lic_dir = Path.home() / ".docmirror" / "licenses"
    lic_dir.mkdir(parents=True, exist_ok=True)

    # Collect all enterprise plugin domains
    from docmirror.plugins import registry
    all_plugins = registry.list_plugins()
    enterprise_domains = [
        name for name in all_plugins
        if getattr(registry.get(name), "edition", "") == "enterprise"
    ]

    import json as _json
    license_info = {
        "license_id": f"DEMO-{uuid.uuid4().hex[:8].upper()}",
        "tier": "enterprise",
        "type": "demo",
        "customer": {"name": "Development Environment", "company": "DocMirror Dev", "email": "dev@docmirror.local"},
        "validity": {
            "issued_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=365)).isoformat(),
            "grace_period_days": 30,
        },
        "features": enterprise_domains,
    }
    # Signature must match _verify_signature: sha256(json.dumps(license_info, sort_keys=True))
    content_str = _json.dumps(license_info, sort_keys=True)
    signature = hashlib.sha256(content_str.encode()).hexdigest()
    license_data = {
        "license_info": license_info,
        "security": {
            "algorithm": "simplified",
            "signature": f"simplified:{signature}",
        },
    }

    lic_path = lic_dir / "demo.lic"
    with open(lic_path, "w") as f:
        json.dump(license_data, f, indent=2, ensure_ascii=False)

    console.print(Panel(
        f"[green]Demo license generated[/green]\n\n"
        f"  License ID: [cyan]{license_data['license_info']['license_id']}[/cyan]\n"
        f"  Tier: [cyan]enterprise (demo)[/cyan]\n"
        f"  Expires: [cyan]{license_data['license_info']['validity']['expires_at']}[/cyan]\n"
        f"  Plugins: [cyan]{len(enterprise_domains)} enterprise domains[/cyan]\n\n"
        f"  Saved to: [yellow]{lic_path}[/yellow]",
        title="Demo License",
        border_style="green",
    ))


# Export for integration
__all__ = ["plugins"]
