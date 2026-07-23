# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

from docmirror.input.canonical.seal import CanonicalValidationError, seal_canonical_result
from docmirror.models.entities.parse_result import ParseResult
from docmirror.models.tracking.mutation import Mutation


def test_canonical_seal_revalidates_and_seals_result():
    result = ParseResult()
    result.record_mutation(
        "GenericEntityExtractor",
        "parse_result",
        "entities.document_type",
        "unknown",
        "generic",
        reason="classification evidence",
    )
    sealed = seal_canonical_result(result)
    assert sealed.verify_integrity()
    assert sealed.mutations[0].middleware_name == "GenericEntityExtractor"


def test_canonical_seal_rejects_unattributed_mutation():
    result = ParseResult()
    result.mutations.append(
        Mutation(
            middleware_name="",
            target_block_id="parse_result",
            field_changed="entities.document_type",
            old_value="unknown",
            new_value="generic",
            reason="missing actor",
        )
    )
    with pytest.raises(CanonicalValidationError, match="no actor"):
        seal_canonical_result(result)
