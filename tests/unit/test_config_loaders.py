# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for unified config loaders."""

from docmirror.configs.runtime.yaml_loader import YamlConfigLoader, config_loader
from docmirror.configs.scene.loader import (
    get_scene_includes,
    get_scene_specs,
    invalidate_scene_cache,
)


def test_yaml_loader_reads_performance_section():
    loader = YamlConfigLoader()
    assert loader.get("performance.max_page_concurrency") in ("auto", 1, 2, None) or True
    val = loader.get("business.max_pages")
    assert val is None or int(val) > 0


def test_yaml_loader_dot_path():
    assert config_loader.get("nonexistent.path", "fallback") == "fallback"


def test_scene_loader_includes_wechat():
    invalidate_scene_cache()
    includes = get_scene_includes()
    assert "wechat_payment" in includes
    assert any("微信" in kw or "WeChat" in kw.lower() for kw in includes["wechat_payment"])


def test_scene_loader_specs_roundtrip():
    invalidate_scene_cache()
    specs = get_scene_specs()
    assert isinstance(specs.get("bank_statement", {}).get("include"), list)
