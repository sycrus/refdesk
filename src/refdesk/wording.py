"""Fixed status wording: the single source for every status label (CLAUDE.md, PRD 8A,
design/design-system.md "Fixed wording").

Operators learn these labels, so they are never paraphrased. The API returns them
verbatim and the UI displays them verbatim. Tests pin each value.
"""

from __future__ import annotations

from enum import StrEnum


class RightsStatus(StrEnum):
    OPEN = "Open (as stated by source)"
    UNVERIFIED = "Unverified"
    PERMISSION_REQUIRED = "Permission required"


class AttributionStatus(StrEnum):
    VERIFIED = "Attribution verified from record"
    NEEDS_HUMAN_CHECK = "Needs human check"


class StopReason(StrEnum):
    """Why a run ended early (PRD 10.2). The value is the machine code; `banner` is the
    StopBanner title."""

    BUDGET_CAP = "budget_cap"
    STEP_CAP = "step_cap"
    TIMEOUT = "timeout"
    NO_PROGRESS = "no_progress"
    POOL_EXHAUSTED = "pool_exhausted"
    SOURCE_UNAVAILABLE = "source_unavailable"
    DECLINED = "declined"
    CANCELLED = "cancelled"

    @property
    def banner(self) -> str:
        return _STOP_BANNERS[self]


_STOP_BANNERS = {
    StopReason.BUDGET_CAP: "Stopped: budget cap reached",
    StopReason.STEP_CAP: "Stopped: step cap reached",
    StopReason.TIMEOUT: "Stopped: timeout",
    StopReason.NO_PROGRESS: "Stopped: no progress",
    StopReason.POOL_EXHAUSTED: "Stopped: no candidates left",
    StopReason.SOURCE_UNAVAILABLE: "Stopped: source unavailable",
    StopReason.DECLINED: "Stopped: request declined",
    StopReason.CANCELLED: "Stopped: cancelled",
}

EXPORTED = "Exported. This board is now read-only"
# Shown on the fit sentence when the judge flags it. It never changes the attribution
# status: that rests on the claims (ADR-022, amended 2026-10-27, issue #135).
OPINION_FLAGGED = "Opinion flagged: may state a fact the record does not give"
NOT_LEGAL_ADVICE = "Rights are recorded as stated by each source. This is not legal advice."
