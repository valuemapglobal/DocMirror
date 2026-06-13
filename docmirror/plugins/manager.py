# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Plugin Manager
==============

High-level API for plugin lifecycle management:
- Enable/disable plugins
- Install/uninstall plugins
- List plugin status
- Detect conflicts

Usage:
    from docmirror.plugins import plugin_manager

    # List all plugins
    plugin_manager.list_all()

    # Disable a plugin
    plugin_manager.disable("id_card")

    # Enable a plugin
    plugin_manager.enable("id_card")

    # Check plugin status
    plugin_manager.status("bank_statement")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PluginManager:
    """Manager for plugin lifecycle operations."""

    def __init__(self, plugins_dir: str | None = None):
        """Initialize plugin manager.

        Args:
            plugins_dir: Path to plugins directory (auto-detect if None)
        """
        if plugins_dir is None:
            # Auto-detect: docmirror/plugins/
            plugins_dir = str(Path(__file__).parent)

        self.plugins_dir = Path(plugins_dir)
        self.state_file = self.plugins_dir / ".plugin_state.json"
        self._state = self._load_state()

    def list_all(self) -> list[dict[str, Any]]:
        """List all plugins with status.

        Returns:
            List of plugin info dicts:
            [
                {
                    "name": "id_card",
                    "display_name": "ID Card (身份证)",
                    "enabled": True,
                    "type": "builtin",
                    "version": "1.0.0"
                },
                ...
            ]
        """
        plugins = []

        for item in self.plugins_dir.iterdir():
            if not item.is_dir() or item.name.startswith("__"):
                continue

            # Check if disabled (starts with _)
            is_enabled = not item.name.startswith("_")
            name = item.name.lstrip("_")

            # Read plugin metadata
            info = self._get_plugin_info(item, name, is_enabled)
            plugins.append(info)

        return sorted(plugins, key=lambda x: x["name"])

    def enable(self, plugin_name: str) -> bool:
        """Enable a plugin.

        Args:
            plugin_name: Plugin name (e.g., "id_card")

        Returns:
            True if successful
        """
        return self._toggle_plugin(plugin_name, enable=True)

    def disable(self, plugin_name: str) -> bool:
        """Disable a plugin.

        Args:
            plugin_name: Plugin name (e.g., "id_card")

        Returns:
            True if successful
        """
        return self._toggle_plugin(plugin_name, enable=False)

    def status(self, plugin_name: str) -> dict[str, Any]:
        """Get plugin status.

        Args:
            plugin_name: Plugin name

        Returns:
            Plugin status dict
        """
        plugins = self.list_all()
        for p in plugins:
            if p["name"] == plugin_name:
                return p

        raise ValueError(f"Plugin '{plugin_name}' not found")

    def is_enabled(self, plugin_name: str) -> bool:
        """Check if plugin is enabled.

        Args:
            plugin_name: Plugin name

        Returns:
            True if enabled
        """
        try:
            return self.status(plugin_name)["enabled"]
        except ValueError:
            return False

    def _toggle_plugin(self, plugin_name: str, enable: bool) -> bool:
        """Toggle plugin enable/disable state.

        Args:
            plugin_name: Plugin name
            enable: True to enable, False to disable

        Returns:
            True if successful
        """
        # Determine current directory name
        enabled_path = self.plugins_dir / plugin_name
        disabled_path = self.plugins_dir / f"_{plugin_name}"

        # Check current state
        if enabled_path.exists():
            current_enabled = True
            old_path = enabled_path
            new_path = disabled_path
        elif disabled_path.exists():
            current_enabled = False
            old_path = disabled_path
            new_path = enabled_path
        else:
            raise ValueError(f"Plugin '{plugin_name}' directory not found")

        # Check if already in desired state
        if current_enabled == enable:
            state = "enabled" if enable else "disabled"
            logger.info(f"[PluginManager] Plugin '{plugin_name}' is already {state}")
            return True

        # Rename directory
        try:
            old_path.rename(new_path)

            # Update state
            self._state[plugin_name] = {"enabled": enable}
            self._save_state()

            state = "enabled" if enable else "disabled"
            logger.info(f"[PluginManager] ✓ Plugin '{plugin_name}' {state}")
            return True

        except Exception as e:
            state = "enable" if enable else "disable"
            logger.error(f"[PluginManager] Failed to {state} plugin '{plugin_name}': {e}")
            return False

    def _get_plugin_info(self, path: Path, name: str, is_enabled: bool) -> dict[str, Any]:
        """Get plugin metadata.

        Args:
            path: Plugin directory path
            name: Plugin name
            is_enabled: Whether plugin is enabled

        Returns:
            Plugin info dict
        """
        info = {
            "name": name,
            "display_name": name.replace("_", " ").title(),
            "enabled": is_enabled,
            "type": "builtin",
            "version": "unknown",
        }

        # Try to read version from plugin.py
        plugin_file = path / "plugin.py"
        if plugin_file.exists():
            try:
                content = plugin_file.read_text()
                # Extract display_name from code
                if "display_name" in content:
                    import re

                    match = re.search(r'display_name.*?return\s+"([^"]+)"', content)
                    if match:
                        info["display_name"] = match.group(1)
            except Exception:
                pass

        return info

    def _load_state(self) -> dict[str, Any]:
        """Load plugin state from file.

        Returns:
            State dict
        """
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"[PluginManager] Failed to load state: {e}")

        return {}

    def _save_state(self) -> None:
        """Save plugin state to file."""
        try:
            with open(self.state_file, "w") as f:
                json.dump(self._state, f, indent=2)
        except Exception as e:
            logger.error(f"[PluginManager] Failed to save state: {e}")


# Global singleton
plugin_manager = PluginManager()

__all__ = ["PluginManager", "plugin_manager"]
