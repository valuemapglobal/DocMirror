# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.tier_contract]

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "tests/external_plugins/reference_provider"


def test_reference_provider_builds_and_loads_without_private_core_imports(tmp_path) -> None:
    provider_source = (PLUGIN / "src/docmirror_reference_provider/provider.py").read_text(encoding="utf-8")
    assert "docmirror.plugins._runtime" not in provider_source
    assert "docmirror.input" not in provider_source
    assert "docmirror.models" not in provider_source
    assert "docmirror.server" not in provider_source

    wheel_dir = tmp_path / "wheel"
    target = tmp_path / "installed"
    wheel_dir.mkdir()
    pip_available = importlib.util.find_spec("pip") is not None
    uv = shutil.which("uv")
    assert pip_available or uv, "external plugin E2E requires either pip or uv"
    build_command = (
        [str(uv), "build", "--wheel", "--out-dir", str(wheel_dir), str(PLUGIN)]
        if uv
        else [sys.executable, "-m", "pip", "wheel", "--no-deps", str(PLUGIN), "-w", str(wheel_dir)]
    )
    subprocess.run(
        build_command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(wheel_dir.glob("docmirror_reference_provider-*.whl"))
    install_command = (
        [str(uv), "pip", "install", "--no-deps", "--target", str(target), str(wheel)]
        if uv
        else [sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(target), str(wheel)]
    )
    subprocess.run(
        install_command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    script = f"""
import json
import sys
from pathlib import Path

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.models.sealed import seal_parse_result
from docmirror.plugins._runtime.discovery import reset_discovery
from docmirror.plugins._runtime.plugin_registry import registry
from docmirror.server.edition_outputs import write_outputs

reset_discovery()
registry._discovered = False
registry._frozen = False
registry._providers.clear()
registry._projectors.clear()
registry._projector_providers.clear()
registry._provider_manifests.clear()
registry._provider_resource_roots.clear()

result = ParseResult(
    status=ResultStatus.SUCCESS,
    entities=DocumentEntities(document_type='reference_document'),
    raw_text='one two three',
)
assert 'docmirror_reference_provider.provider' not in sys.modules
sealed = seal_parse_result(result)
before = sealed.fact_fingerprint()
assert 'docmirror_reference_provider.provider' not in sys.modules

providers = [p for p in registry.list_providers() if p.provider_id == 'reference-provider']
assert len(providers) == 1, providers
provider = providers[0]
assert provider.projectors[0].edition == 'enterprise'
assert 'docmirror_reference_provider.provider' in sys.modules
resource = registry.read_provider_resource('reference-provider', 'output_template')
assert resource is not None and 'reference_document' in resource

output_root = Path({str(tmp_path / 'artifacts')!r})
task_id, written = write_outputs(
    sealed,
    output_root,
    task_id='external_plugin_e2e',
    overwrite=True,
)
assert task_id == 'external_plugin_e2e'
assert {{'mirror', 'community', 'content', 'datasets', 'enterprise'}} <= set(written), written
community = json.loads(written['community'].read_text(encoding='utf-8'))
assert community['document']['type'] == 'reference_document'
enterprise = json.loads(written['enterprise'].read_text(encoding='utf-8'))
assert enterprise['data']['reference_word_count'] == 3
assert enterprise['sealed_fact_fingerprint'] == before
assert sealed.fact_fingerprint() == before
assert 'reference_word_count' not in sealed.to_read_view().entities.domain_specific
print('reference provider e2e passed')
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join((str(target), str(ROOT)))
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "reference provider e2e passed" in completed.stdout
