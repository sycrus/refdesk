"""Request and response models for the HTTP API (PRD 13A). This is the contract: the
OpenAPI spec in docs/api/openapi.json is generated from these models.

Validation that protects a gate lives here too, so a client cannot skip it: approval needs
an explicit acknowledgement, and keeping a flagged item needs a note (PRD 8B, G3 and G4).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from refdesk.schema import ArtworkRecord
from refdesk.wording import AttributionStatus, StopReason

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Enums


class UsageMode(StrEnum):
    REFERENCE_ONLY = "reference_only"
    REPRODUCTION = "reproduction"  # needs rights basis, credit line and resolution check


class LoopState(StrEnum):
    """The loop controller's states (PRD 10.2 state diagram)."""

    INIT = "init"
    RETRIEVE = "retrieve"
    DECIDE = "decide"
    GENERATE = "generate"
    VERIFY = "verify"
    ASSEMBLE = "assemble"
    HUMAN_CHECK = "human_check"
    EXPORT = "export"
    DONE = "done"
    STOPPED = "stopped"
    CANCELLED = "cancelled"


class GateId(StrEnum):
    G0_INTAKE = "G0"
    G1_SPEND = "G1"
    G2_VERIFY = "G2"
    G3_REVIEW = "G3"
    G4_APPROVE = "G4"
    G5_EXPORT = "G5"


class GateState(StrEnum):
    PASSED = "passed"
    ACTIVE = "active"
    PENDING = "pending"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class ErrorType(StrEnum):
    ATTRIBUTION = "attribution"
    RIGHTS = "rights"
    IRRELEVANT = "irrelevant"
    RATIONALE = "rationale"


# Requests


class Conditions(_Model):
    period: str | None = None
    material: str | None = None
    motif: str | None = None
    department: str | None = None


class BoardRequest(_Model):
    """S1 New board."""

    brief: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    avoid: list[NonEmpty] = []
    usage_mode: UsageMode = UsageMode.REFERENCE_ONLY
    anchor_id: str | None = Field(None, description="'<source>:<object_id>' of an anchor work")
    conditions: Conditions = Conditions()
    novelty: float = Field(0.5, ge=0, le=1, description="0 = familiar, 1 = unexpected")
    keep_local: bool = Field(False, description="Never send this brief to a cloud provider")
    budget_cap_usd: float = Field(0.05, gt=0, description="Spend cap for this board")
    target_items: int = Field(12, ge=1, le=50)


class ReviewDecision(_Model):
    item_id: NonEmpty
    decision: Literal["keep", "drop"]
    note: str | None = None

    @model_validator(mode="after")
    def _keep_needs_a_note(self) -> ReviewDecision:
        if self.decision == "keep" and not (self.note and self.note.strip()):
            raise ValueError("keeping a flagged item requires a note (G3)")
        return self


class ReviewRequest(_Model):
    """G3: decisions on items in "Needs human check"."""

    decisions: list[ReviewDecision]


class CapRaise(_Model):
    """G1: an explicit, recorded decision to raise the spend cap and resume."""

    new_cap_usd: float = Field(gt=0)
    raised_by: NonEmpty


class ApprovalRequest(_Model):
    """G4: rights are as stated by each source; this is not legal advice."""

    approver: NonEmpty
    acknowledged: Literal[True] = Field(description="Must be true to approve")


class ExportRequest(_Model):
    """G5: irreversible. Requires an approval record."""

    format: Literal["csv", "pdf"] = "csv"


class ErrorReport(_Model):
    """S8: "This is wrong". Queued for human review, then may feed the golden set."""

    run_id: str | None = None
    item_id: NonEmpty
    error_type: ErrorType
    note: NonEmpty


# Responses


class Cost(_Model):
    spent_usd: float
    cap_usd: float
    currency: Literal["USD"] = "USD"


class Gate(_Model):
    id: GateId
    state: GateState
    status_text: str
    actor: str | None = Field(None, description="Who must act, for human gates")


class Confidence(_Model):
    bucket: Literal["high", "medium", "low"]
    value: float = Field(ge=0, le=1, description="Calibrated probability, shown on hover")


class Evidence(_Model):
    field: str = Field(description="Record field that supports the rationale, e.g. 'medium'")
    value: str
    record_url: str | None = None


class BoardItem(_Model):
    record: ArtworkRecord
    rationale: str | None
    evidence: list[Evidence]
    attribution_status: AttributionStatus
    flag_reasons: list[str] = Field([], description="Why the item needs a human check")
    confidence: Confidence | None = None
    tier_used: str | None = None
    cost_usd: float = 0.0
    selected: bool = False
    score: float | None = Field(None, description="Retrieval score; higher ranks first")
    score_components: dict[str, float] = Field(
        {}, description="Named parts of the score that sum to it, e.g. similarity, attributes"
    )


class RunCreated(_Model):
    run_id: str
    state: LoopState


class RunView(_Model):
    run_id: str
    request: BoardRequest | None = Field(None, description="What was asked (S3 header)")
    state: LoopState
    stop_reason: StopReason | None = None
    stop_banner: str | None = Field(None, description="Fixed wording; never hidden")
    stop_detail: str | None = Field(None, description="What exactly stopped the run")
    gates: list[Gate]
    items: list[BoardItem]
    cost: Cost
    keep_local: bool
    sent_to: list[str] = Field([], description="Providers this brief was sent to")
    models_used: dict[str, str] = Field(
        {}, description="Model each role reported, e.g. generator and judge"
    )
    read_only: bool = False


class ExportReceipt(_Model):
    run_id: str
    file: str
    exported_at: datetime
    approver: str
    versions: dict[str, str] = Field(description="Model, adapter and config versions")
    notice: str
    not_legal_advice: str


class ReportAccepted(_Model):
    report_id: str
    status: Literal["queued for review"] = "queued for review"


class GateBlocked(_Model):
    gate: GateId
    reason: str


class Problem(_Model):
    code: str
    message: str


class Health(_Model):
    status: Literal["ok"] = "ok"


class Readiness(_Model):
    ready: bool
    checks: dict[str, str] = Field(description="metadata_store, embedding_index, model_backend")
