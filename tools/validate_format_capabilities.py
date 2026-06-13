#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate format_capabilities.yaml and enhancement_profiles.yaml consistency."""

from __future__ import annotations

import importlib
import sys

from docmirror.configs.format.enhancement import resolve_enhancement_profile, transport_to_content_model
from docmirror.configs.format.loader import load_enhancement_profiles, load_format_registry
from docmirror.framework.orchestrator import MIDDLEWARE_REGISTRY

_KNOWN_OPTIONAL = frozenset({"SLMEntityExtractor"})  # appended when DOCMIRROR_ENABLE_SLM=1


def main() -> int:
    errors: list[str] = []
    caps, ext_map, mime_map = load_format_registry()
    profiles, transport_fallback = load_enhancement_profiles()

    if not caps:
        errors.append("No capabilities loaded")
        return 1

    for cap_id, cap in caps.items():
        if cap.status != "supported":
            continue
        if cap.binding is None or not cap.binding.adapter:
            errors.append(f"{cap_id}: supported but missing adapter binding")
            continue
        ref = cap.binding.adapter
        module_path, _, class_name = ref.rpartition(".")
        try:
            mod = importlib.import_module(module_path)
            getattr(mod, class_name)
        except Exception as exc:
            errors.append(f"{cap_id}: cannot import adapter {ref}: {exc}")

        if cap.binding.fallback:
            fb_ref = cap.binding.fallback.adapter
            fb_mod, _, fb_cls = fb_ref.rpartition(".")
            try:
                getattr(importlib.import_module(fb_mod), fb_cls)
            except Exception as exc:
                errors.append(f"{cap_id}: cannot import fallback adapter {fb_ref}: {exc}")

        model = cap.content_model
        if model not in profiles:
            errors.append(f"{cap_id}: content_model {model!r} missing from enhancement_profiles")
        elif "standard" not in profiles[model]:
            errors.append(f"{cap_id}: no standard profile for {model}")

    for transport, model in transport_fallback.items():
        if model not in profiles:
            errors.append(f"transport_fallback {transport}: unknown content_model {model}")
        _ = resolve_enhancement_profile(model, "standard")

    for model, modes in profiles.items():
        for mode, names in modes.items():
            for name in names:
                if name in _KNOWN_OPTIONAL:
                    continue
                if name not in MIDDLEWARE_REGISTRY:
                    errors.append(
                        f"enhancement_profiles {model}.{mode}: unknown middleware {name!r}"
                    )

    seen_ext: set[str] = set()
    for ext, cid in ext_map.items():
        if ext in seen_ext:
            errors.append(f"duplicate extension mapping: {ext}")
        seen_ext.add(ext)

    if errors:
        print("FCR validation FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(
        f"FCR validation OK: {len(caps)} capabilities, "
        f"{len([c for c in caps.values() if c.status == 'supported'])} supported, "
        f"{len(ext_map)} extensions, {len(mime_map)} mime rules, "
        f"{len(profiles)} enhancement profiles"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
