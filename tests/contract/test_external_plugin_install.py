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
        [sys.executable, "-m", "pip", "wheel", "--no-deps", str(PLUGIN), "-w", str(wheel_dir)]
        if pip_available
        else [str(uv), "build", "--wheel", "--out-dir", str(wheel_dir), str(PLUGIN)]
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
        [sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(target), str(wheel)]
        if pip_available
        else [str(uv), "pip", "install", "--no-deps", "--target", str(target), str(wheel)]
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
from pathlib import Path

from docmirror.input.canonical.fact_patch import apply_fact_patch
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.models.sealed import seal_parse_result
from docmirror.plugins._runtime.discovery import load_plugin_providers, reset_discovery
from docmirror.plugins._runtime.runner import run_fact_recognition_sync
from docmirror.server.edition_outputs import write_outputs

reset_discovery()
providers = [p for p in load_plugin_providers() if p.provider_id == 'reference-provider']
assert len(providers) == 1, providers
provider = providers[0]
assert provider.recognizers[0].domain_name == 'reference_document'
assert not provider.projectors

result = ParseResult(
    status=ResultStatus.SUCCESS,
    entities=DocumentEntities(document_type='reference_document'),
    text='one two three',
)
patch = run_fact_recognition_sync(result, full_text='one two three')
assert patch.provider_id == 'reference-provider', patch
assert patch.domain_facts['reference_word_count'] == 3
canonical = apply_fact_patch(result, patch)
sealed = seal_parse_result(canonical)
before = sealed.fact_fingerprint()
output_root = Path({str(tmp_path / 'artifacts')!r})
task_id, written = write_outputs(
    sealed,
    output_root,
    task_id='external_plugin_e2e',
    overwrite=True,
)
assert task_id == 'external_plugin_e2e'
assert {{'mirror', 'community', 'content', 'datasets'}} <= set(written), written
community = json.loads(written['community'].read_text(encoding='utf-8'))
assert community['document']['type'] == 'reference_document'
items = [item for section in community['sections'] for item in section.get('items', [])]
assert any(item.get('key') == 'reference_word_count' and item.get('value') == 3 for item in items), items
assert sealed.fact_fingerprint() == before
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
