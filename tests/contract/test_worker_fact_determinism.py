# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio

import pytest

from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.input.entry.options import normalize_parse_policy

pytestmark = [pytest.mark.contract, pytest.mark.tier_contract]


def test_same_source_and_policy_have_same_fact_fingerprint_across_workers(tmp_path) -> None:
    source = tmp_path / "worker-determinism.txt"
    source.write_text("名称：示例公司\n统一社会信用代码：91310000TEST000001\n", encoding="utf-8")
    policy = normalize_parse_policy(mode="balanced", doc_type_hint="business_license:force")

    fingerprints = []
    for workers in (1, 2, 4, None):
        sealed = asyncio.run(
            perceive_document(
                source,
                PerceiveOptions(policy=policy, max_workers=workers),
            )
        )
        fingerprints.append(sealed.fact_fingerprint())

    assert len(set(fingerprints)) == 1
