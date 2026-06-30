# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DocMirror Document Runtime Contract (DRC) package.

GA 1.0 §6: DRC is the unified runtime contract shared by CLI, API, SDK, and
Task entries. It provides work unit planning, progress event accounting,
checkpoint persistence, batch scheduling, cost profiles, and runtime metrics.

Modules:
- control: RuntimeControl, CostProfile, CheckpointControl, etc.
- events: ProgressEvent, FallbackEvent, MetricEvent
- work_units: WorkUnit, BatchJobLedger, WorkUnitPlanner
- ledger: Atomic event/checkpoint writing, manifest v2 helpers
- checkpoint: Checkpoint persistence, fingerprint, resume validation
- scheduler: Worker budget, parallel execution, retry, backpressure
- artifacts: Page/chunk intermediate artifact writer and finalizer
- profiles: Compact/full/forensic profile resolver
- metrics: Throughput, latency, memory, token, artifact size
"""

from docmirror.runtime.artifacts import (
    ArtifactFinalizer,
    IntermediateArtifactWriter,
)
from docmirror.runtime.checkpoint import CheckpointManager
from docmirror.runtime.control import (
    CheckpointControl,
    CostProfileType,
    LongDocumentControl,
    ProgressControl,
    RetryControl,
    RuntimeControl,
    StreamingControl,
    TaskMode,
    TokenBudget,
    classify_document_size,
    resolve_task_mode,
)
from docmirror.runtime.events import (
    EventStatus,
    FallbackEvent,
    MetricEvent,
    ProgressEvent,
)
from docmirror.runtime.ledger import (
    EventLedger,
    build_manifest_v2,
)
from docmirror.runtime.metrics import (
    MetricsCollector,
    RuntimeMetrics,
    estimate_tokens,
)
from docmirror.runtime.profiles import (
    COMPACT_PROFILE,
    FORENSIC_PROFILE,
    FULL_PROFILE,
    ProfileResolution,
    profile_diff,
    profile_from_cli,
    resolve_profile,
)
from docmirror.runtime.progress_bus import (
    PhaseWeight,
    ProgressBus,
    ProgressCallback,
    ProgressSignal,
)
from docmirror.runtime.scheduler import (
    RuntimeScheduler,
    SchedulerConfig,
)
from docmirror.runtime.work_units import (
    BatchJobEntry,
    BatchJobLedger,
    UnitStatus,
    UnitType,
    WorkUnit,
    WorkUnitPlanner,
    compute_input_digest,
)

__all__ = [
    # control
    "CheckpointControl",
    "CostProfileType",
    "LongDocumentControl",
    "ProgressControl",
    "RetryControl",
    "RuntimeControl",
    "StreamingControl",
    "TaskMode",
    "TokenBudget",
    "classify_document_size",
    "resolve_task_mode",
    # checkpoint
    "CheckpointManager",
    # artifacts
    "ArtifactFinalizer",
    "IntermediateArtifactWriter",
    # metrics
    "MetricsCollector",
    "RuntimeMetrics",
    "estimate_tokens",
    # progress_bus
    "ProgressBus",
    "ProgressCallback",
    "ProgressSignal",
    "PhaseWeight",
    # profiles
    "COMPACT_PROFILE",
    "FULL_PROFILE",
    "FORENSIC_PROFILE",
    "ProfileResolution",
    "profile_diff",
    "profile_from_cli",
    "resolve_profile",
    # scheduler
    "RuntimeScheduler",
    "SchedulerConfig",
    # events
    "EventStatus",
    "FallbackEvent",
    "MetricEvent",
    "ProgressEvent",
    # ledger
    "EventLedger",
    "build_manifest_v2",
    # work_units
    "BatchJobEntry",
    "BatchJobLedger",
    "UnitStatus",
    "UnitType",
    "WorkUnit",
    "WorkUnitPlanner",
    "compute_input_digest",
]
