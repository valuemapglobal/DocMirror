# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""PerceiveResult envelope tests."""

from __future__ import annotations

from docmirror.core.entry.perceive_result import PerceiveResult
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus


def test_perceive_result_delegates_to_mirror():
    mirror = ParseResult(status=ResultStatus.SUCCESS)
    mirror.entities = DocumentEntities(document_type="id_card")
    env = PerceiveResult(mirror=mirror)
    assert env.mirror.entities.document_type == "id_card"
    assert env.mirror is mirror
