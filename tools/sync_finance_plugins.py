#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generate docmirror_finance/plugins/* from docmirror_enterprise/plugins/* baselines."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENTERPRISE_PLUGINS = REPO / "docmirror_enterprise" / "plugins"
FINANCE_PLUGINS = REPO / "docmirror_finance" / "plugins"
SKIP = frozenset({"alipay_payment"})  # full finance implementation kept as-is

PLUGIN_TEMPLATE = '''\
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Finance edition plugin for {domain_name}."""

from docmirror_finance.plugins._baseline import make_finance_plugin

plugin = make_finance_plugin(
    domain_name="{domain_name}",
    display_name="{display_name}",
)
'''


def _enterprise_domains() -> list[tuple[str, str]]:
    import docmirror_enterprise.plugins as ep_pkg

    rows: list[tuple[str, str]] = []
    for _, modname, ispkg in pkgutil.iter_modules(ep_pkg.__path__):
        if not ispkg or modname.startswith("_"):
            continue
        mod = importlib.import_module(f"docmirror_enterprise.plugins.{modname}.plugin")
        rows.append((modname, mod.plugin.display_name))
    return sorted(rows, key=lambda item: item[0])


def main() -> int:
    from docmirror_finance.plugins._baseline import to_finance_display_name

    domains = _enterprise_domains()
    if len(domains) != 120:
        print(f"WARN: expected 120 enterprise domains, got {len(domains)}")

    created = 0
    skipped = 0
    for domain_name, enterprise_display in domains:
        if domain_name in SKIP:
            skipped += 1
            continue
        dest = FINANCE_PLUGINS / domain_name
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "__init__.py").write_text("", encoding="utf-8")
        display_name = to_finance_display_name(enterprise_display)
        content = PLUGIN_TEMPLATE.format(
            domain_name=domain_name,
            display_name=display_name.replace('"', '\\"'),
        )
        (dest / "plugin.py").write_text(content, encoding="utf-8")
        created += 1

    print(f"sync_finance_plugins: created/updated {created}, skipped {skipped} (custom plugins)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
