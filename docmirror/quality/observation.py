# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Quality Observation Event — QTC §6.1.

Every parse or benchmark run produces a QualityObservationEvent that captures:
- Input identity and fixture metadata
- Pipeline decision and adapter routing
- Output artifact statuses (Mirror, Markdown, Community, Evidence)
- Four-layer fidelity metrics (text, layout, business, audit)
- Failure envelope (silent failure, error code, warnings, page outcomes)

This event is the fundamental unit of the Quality & Trust Contract (QTC).
Events flow into the BucketedMetricsAggregator to produce GA metrics reports.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


# ── Sub-models ──────────────────────────────────────────────────────────────


@dataclass
class RunMetadata:
    """Execution context that produced this observation."""
    commit: str = ""
    parser_version: str = ""
    profile: str = "standard"
    cpu_only: bool = False
    license_state: str = "valid"  # missing | valid | not_required


@dataclass
class InputIdentity:
    """Fixture identity and classification."""
    fixture_id: str = ""
    document_type: str = ""
    domain: str = "generic"
    format: str = ""
    quality_bucket: str = "medium"  # easy | medium | hard | broken | low_quality | edge_case
    fixture_source: str = "synthetic"  # public | synthetic | desensitized_real | customer_regression | golden_benchmark | adversarial


@dataclass
class PipelineDecision:
    """Which capability and adapter handled this input."""
    capability_id: str = ""
    adapter: str = ""
    pipeline_decision_id: str = ""
    fallbacks: list[str] = field(default_factory=list)


@dataclass
class ArtifactStatus:
    """Status of a single output artifact.

    GA 1.0 SS4.12 C4: partial_result carries page-level partial success
    metadata when some pages failed but others succeeded.
    """
    status: str = "not_generated"  # success | partial | failure | not_generated
    schema_valid: bool | None = None
    readable: bool | None = None
    partial_result: dict[str, Any] | None = None


@dataclass
class OutputStatuses:
    """Status of all output artifacts."""
    mirror: ArtifactStatus = field(default_factory=ArtifactStatus)
    markdown: ArtifactStatus = field(default_factory=ArtifactStatus)
    community: ArtifactStatus = field(default_factory=ArtifactStatus)
    evidence: ArtifactStatus = field(default_factory=ArtifactStatus)


@dataclass
class FidelityLayer:
    """Standard shape for each fidelity layer (text, layout, business, audit)."""
    score: float = 0.0
    status: str = "not_measured"  # pass | fail | not_measured
    metrics: dict[str, float] = field(default_factory=dict)
    denominator: int = 0
    failed_items: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)


@dataclass
class FidelityLedger:
    """Four-layer fidelity ledger."""
    text: FidelityLayer = field(default_factory=FidelityLayer)
    layout: FidelityLayer = field(default_factory=FidelityLayer)
    business: FidelityLayer = field(default_factory=FidelityLayer)
    audit: FidelityLayer = field(default_factory=FidelityLayer)


@dataclass
class PageOutcome:
    """Outcome for a single page."""
    page: int = 0
    status: str = "success"  # success | partial | failure
    error_code: str | None = None


@dataclass
class FailureEnvelope:
    """Captures all failure and warning signals for this observation.

    GA 1.0 SS4.12 C4: partial_result_envelope carries the full partial result
    metadata (total_pages, success_count, failed_page_details, etc.) so
    downstream consumers know exactly which pages succeeded and which failed.
    """
    silent_failure: bool = False
    error_code: str | None = None
    warnings: list[str] = field(default_factory=list)
    partial_pages: list[PageOutcome] = field(default_factory=list)
    retained_success_pages: bool = True
    partial_result_envelope: dict[str, Any] | None = None


# ── Main model ───────────────────────────────────────────────────────────────


@dataclass
class QualityObservationEvent:
    """Single observation produced by a parse or benchmark run.

    This is the atomic unit of the QTC. Every fixture run generates one event.
    Events are collected (as JSONL) and fed to the BucketedMetricsAggregator
    to produce bucketed GA metrics reports.

    Design reference: docs/design/GA1.0/08_accuracy_trust_ga_gap_closure_plan.md §6.1
    """
    version: int = 1
    observation_id: str = ""
    generated_at: str = ""
    run: RunMetadata = field(default_factory=RunMetadata)
    input: InputIdentity = field(default_factory=InputIdentity)
    pipeline: PipelineDecision = field(default_factory=PipelineDecision)
    outputs: OutputStatuses = field(default_factory=OutputStatuses)
    fidelity: FidelityLedger = field(default_factory=FidelityLedger)
    failure: FailureEnvelope = field(default_factory=FailureEnvelope)

    def __post_init__(self):
        """Auto-fill computed fields if empty."""
        if not self.observation_id:
            self.observation_id = f"qobs_{uuid.uuid4().hex[:16]}"
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()

    @classmethod
    def from_dict(cls, d: dict) -> "QualityObservationEvent":
        """Construct a QualityObservationEvent from a JSON/dict representation."""
        run_d = d.get("run", {})
        inp_d = d.get("input", {})
        pipe_d = d.get("pipeline", {})
        out_d = d.get("outputs", {})
        fid_d = d.get("fidelity", {})
        fail_d = d.get("failure", {})

        return cls(
            version=d.get("version", 1),
            observation_id=d.get("observation_id", ""),
            generated_at=d.get("generated_at", ""),
            run=RunMetadata(
                commit=run_d.get("commit", ""),
                parser_version=run_d.get("parser_version", ""),
                profile=run_d.get("profile", "standard"),
                cpu_only=run_d.get("cpu_only", False),
                license_state=run_d.get("license_state", "valid"),
            ),
            input=InputIdentity(
                fixture_id=inp_d.get("fixture_id", ""),
                document_type=inp_d.get("document_type", ""),
                domain=inp_d.get("domain", "generic"),
                format=inp_d.get("format", ""),
                quality_bucket=inp_d.get("quality_bucket", "medium"),
                fixture_source=inp_d.get("fixture_source", "synthetic"),
            ),
            pipeline=PipelineDecision(
                capability_id=pipe_d.get("capability_id", ""),
                adapter=pipe_d.get("adapter", ""),
                pipeline_decision_id=pipe_d.get("pipeline_decision_id", ""),
                fallbacks=pipe_d.get("fallbacks", []),
            ),
            outputs=OutputStatuses(
                mirror=_build_artifact(out_d.get("mirror", {})),
                markdown=_build_artifact(out_d.get("markdown", {})),
                community=_build_artifact(out_d.get("community", {})),
                evidence=_build_artifact(out_d.get("evidence", {})),
            ),
            fidelity=_build_fidelity(fid_d),
            failure=_build_failure(fail_d),
        )



# ── Factory helpers ──────────────────────────────────────────────────────────


def new_observation_event(
    *,
    fixture_id: str = "",
    document_type: str = "",
    domain: str = "generic",
    format: str = "",
    quality_bucket: str = "medium",
    fixture_source: str = "synthetic",
    adapter: str = "",
    capability_id: str = "",
    commit: str = "",
    parser_version: str = "",
    profile: str = "standard",
    cpu_only: bool = False,
    license_state: str = "valid",
) -> QualityObservationEvent:
    """Create a QualityObservationEvent with sensible defaults.

    Only the fields most callers care about are exposed; everything else
    defaults to empty/not_measured and can be populated after creation.
    """
    return QualityObservationEvent(
        run=RunMetadata(
            commit=commit,
            parser_version=parser_version,
            profile=profile,
            cpu_only=cpu_only,
            license_state=license_state,
        ),
        input=InputIdentity(
            fixture_id=fixture_id,
            document_type=document_type,
            domain=domain,
            format=format,
            quality_bucket=quality_bucket,
            fixture_source=fixture_source,
        ),
        pipeline=PipelineDecision(
            capability_id=capability_id,
            adapter=adapter,
        ),
    )


# ── Serialization ────────────────────────────────────────────────────────────


def observation_to_dict(event: QualityObservationEvent) -> dict[str, Any]:
    """Serialize a QualityObservationEvent to a plain dict (for JSON/JSONL output)."""
    d = asdict(event)
    # Remove empty optional fields for cleaner output
    return _strip_none(d)


def _strip_none(d: dict[str, Any]) -> dict[str, Any]:
    """Recursively remove None values and empty collections from a dict."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, list) and len(v) == 0:
            continue
        if isinstance(v, dict):
            cleaned = _strip_none(v)
            if cleaned:
                out[k] = cleaned
        else:
            out[k] = v
    return out


def observation_from_dict(data: dict[str, Any]) -> QualityObservationEvent:
    """Deserialize a dict back into a QualityObservationEvent."""
    return QualityObservationEvent(
        version=data.get("version", 1),
        observation_id=data.get("observation_id", ""),
        generated_at=data.get("generated_at", ""),
        run=_build_run(data.get("run", {})),
        input=_build_input(data.get("input", {})),
        pipeline=_build_pipeline(data.get("pipeline", {})),
        outputs=_build_outputs(data.get("outputs", {})),
        fidelity=_build_fidelity(data.get("fidelity", {})),
        failure=_build_failure(data.get("failure", {})),
    )


def _build_run(d: dict) -> RunMetadata:
    return RunMetadata(**{k: d.get(k, getattr(RunMetadata(), k)) for k in ("commit", "parser_version", "profile", "cpu_only", "license_state")})


def _build_input(d: dict) -> InputIdentity:
    return InputIdentity(**{k: d.get(k, getattr(InputIdentity(), k)) for k in ("fixture_id", "document_type", "domain", "format", "quality_bucket", "fixture_source")})


def _build_pipeline(d: dict) -> PipelineDecision:
    return PipelineDecision(
        capability_id=d.get("capability_id", ""),
        adapter=d.get("adapter", ""),
        pipeline_decision_id=d.get("pipeline_decision_id", ""),
        fallbacks=d.get("fallbacks", []),
    )


def _build_outputs(d: dict) -> OutputStatuses:
    return OutputStatuses(
        mirror=_build_artifact(d.get("mirror", {})),
        markdown=_build_artifact(d.get("markdown", {})),
        community=_build_artifact(d.get("community", {})),
        evidence=_build_artifact(d.get("evidence", {})),
    )


def _build_artifact(d: dict) -> ArtifactStatus:
    return ArtifactStatus(
        status=d.get("status", "not_generated"),
        schema_valid=d.get("schema_valid"),
        readable=d.get("readable"),
    )


def _build_fidelity(d: dict) -> FidelityLedger:
    return FidelityLedger(
        text=_build_layer(d.get("text", {})),
        layout=_build_layer(d.get("layout", {})),
        business=_build_layer(d.get("business", {})),
        audit=_build_layer(d.get("audit", {})),
    )


def _build_layer(d: dict) -> FidelityLayer:
    return FidelityLayer(
        score=d.get("score", 0.0),
        status=d.get("status", "not_measured"),
        metrics=d.get("metrics", {}),
        denominator=d.get("denominator", 0),
        failed_items=d.get("failed_items", []),
        evidence_refs=d.get("evidence_refs", []),
    )


def _build_failure(d: dict) -> FailureEnvelope:
    pages = d.get("partial_pages", [])
    return FailureEnvelope(
        silent_failure=d.get("silent_failure", False),
        error_code=d.get("error_code"),
        warnings=d.get("warnings", []),
        partial_pages=[PageOutcome(**p) for p in pages] if pages else [],
        retained_success_pages=d.get("retained_success_pages", True),
    )
