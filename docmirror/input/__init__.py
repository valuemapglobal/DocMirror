# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Input Acceptance Module — pre-dispatcher probes and gates."""

from docmirror.input.acceptance import accept_source, check_input_acceptance
from docmirror.input.models import (
    AcceptedSource,
    CapabilityReport,
    InputAcceptanceReport,
    InputDecisionReport,
    InputProbeReport,
    InputRejectedError,
    ResourceGateReport,
    SafetyGateReport,
)

__all__ = [
    "accept_source",
    "check_input_acceptance",
    "AcceptedSource",
    "InputRejectedError",
    "InputAcceptanceReport",
    "ResourceGateReport",
    "SafetyGateReport",
    "CapabilityReport",
    "InputProbeReport",
    "InputDecisionReport",
]
