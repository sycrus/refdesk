"""Loop controller: the PRD 10.2 state machine in plain Python (issue #155; PRD 10.4 stage 1).

What it does: it decides what happens next in a board run. Each round goes
Retrieve -> Decide -> Generate -> Verify, then either loops back for more candidates,
assembles the board, or stops. It counts an item as accepted only when the verifier
passes it (code checks and the cross-family judge), and builds towards K accepted items.
Before each step and before every model call it checks the kill switch, the wall clock
and (through the LLM client) the budget, so every stop happens *before* the next costly
action. Each stop carries a `StopReason`, whose fixed banner wording lives in
`wording.py`, and a detail sentence; nothing stops silently.

What breaks without it: a board would be one fixed retrieve, generate, verify pass. A
round where every item fails verification would still end "done"; there would be no step
cap, no timeout, no stuck rule and no kill switch; and the budget cap would be per pass,
not per board.

States (PRD 10.2): Init, Retrieve, Decide, Generate, Verify, Assemble, Stopped,
Cancelled. A stopped run still assembles its partial board (Stopped -> Assemble), so the
reason it is partial is shown next to it. A cancelled run does not assemble and can
never be approved or exported. HumanCheck, Export and Done belong to the gates after the
loop (PRD 8B); `LoopState.DONE` marks a loop that assembled without a stop.

Decide is a pass-through to the configured generator tier until the router exists
(M4-13, #165). Values (step cap, timeout, stuck rule, K, cap) come from
`config/loop.yaml`, placeholders until Joe sets them (M4-02, #154).

Not here yet: dropping an item after two failed verifications needs a regeneration
retry, which the loop does not do (each candidate is generated once);
`drop_after_failed_verifications` is loaded so M4-02 can set it. Checkpoint and resume
is M4-05 (#157); the events log is M4-04 (#156).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from refdesk.api.models import LoopState
from refdesk.reasoning import Interrupted, ItemReasoning, Reasoner
from refdesk.schema import ArtworkRecord
from refdesk.verifier import item_status
from refdesk.wording import AttributionStatus, StopReason

S = LoopState


@dataclass(frozen=True)
class LoopConfig:
    """Stop-condition values (PRD 10.2). Placeholders until M4-02 (#154)."""

    max_rounds: int  # step cap: retrieval rounds per run
    timeout_s: float  # wall-clock limit per run
    stuck_rounds: int  # stop after this many consecutive rounds with no new accepted item
    target_items: int  # K: the default for BoardRequest.target_items
    budget_cap_usd: float  # the default for BoardRequest.budget_cap_usd
    drop_after_failed_verifications: int  # not enforced yet: see the module note

    @classmethod
    def load(cls, path: str | Path = "config/loop.yaml") -> LoopConfig:
        values = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(**values["loop"])


@dataclass
class LoopResult:
    state: LoopState = S.INIT
    stop: StopReason | None = None
    stop_detail: str | None = None
    trace: list[LoopState] = field(default_factory=list)  # every state entered, in order
    records: list[ArtworkRecord] = field(default_factory=list)  # every candidate reasoned
    items: dict[str, ItemReasoning] = field(default_factory=dict)
    rounds: int = 0
    tiers: list[str] = field(default_factory=list)  # Decide's choice per round
    spent_usd: float = 0.0
    sent_to: list[str] = field(default_factory=list)
    models_used: dict[str, str] = field(default_factory=dict)

    def status(self, record_id: str) -> AttributionStatus:
        r = self.items[record_id]
        return item_status(r.code, r.judged.verdict if r.judged else None)

    @property
    def accepted(self) -> int:
        return sum(1 for rid in self.items if self.status(rid) is AttributionStatus.VERIFIED)


class LoopController:
    def __init__(
        self,
        config: LoopConfig,
        reasoner: Reasoner,
        *,
        clock: Callable[[], float] = time.monotonic,
        cancelled: Callable[[], bool] = lambda: False,
        on_state: Callable[[LoopState, LoopResult], None] = lambda state, result: None,
    ):
        self.config = config
        self.reasoner = reasoner
        self.clock = clock
        self.cancelled = cancelled  # the kill switch, polled before each step and call
        self.on_state = on_state  # lets the board service show the current state

    def run(
        self,
        *,
        brief: str,
        retrieve: Callable[[int], list[ArtworkRecord]],
        target: int,
        keep_local: bool,
        cap_usd: float,
    ) -> LoopResult:
        """`retrieve(n)` returns up to n candidates not handed out before; an empty list
        means the pool is exhausted."""
        result = LoopResult()
        started = self.clock()

        def enter(state: LoopState) -> None:
            result.state = state
            result.trace.append(state)
            self.on_state(state, result)

        def stop(reason: StopReason, detail: str) -> LoopResult:
            result.stop, result.stop_detail = reason, detail
            if reason is StopReason.CANCELLED:
                enter(S.CANCELLED)  # no Assemble: a cancelled run has no board to approve
                return result
            enter(S.STOPPED)
            enter(S.ASSEMBLE)  # the partial board, with the stop reason beside it
            result.state = S.STOPPED
            return result

        def guard() -> None:
            """Before every step and every model call: kill switch, then wall clock."""
            if self.cancelled():
                raise Interrupted(StopReason.CANCELLED, "Cancelled by the operator.")
            elapsed = self.clock() - started
            if elapsed >= self.config.timeout_s:
                raise Interrupted(
                    StopReason.TIMEOUT,
                    f"The run took {elapsed:.0f} s; the limit is {self.config.timeout_s:.0f} s.",
                )

        enter(S.INIT)
        no_progress = 0
        try:
            while True:
                guard()
                if result.rounds >= self.config.max_rounds:
                    return stop(
                        StopReason.STEP_CAP,
                        f"{result.rounds} retrieval rounds, the most allowed; "
                        f"{result.accepted} of {target} items accepted.",
                    )
                enter(S.RETRIEVE)
                candidates = retrieve(target - result.accepted)
                result.rounds += 1
                if not candidates:
                    if not result.records:
                        return stop(
                            StopReason.POOL_EXHAUSTED,
                            "No record matched the brief, conditions and rights filter.",
                        )
                    result.stop = StopReason.POOL_EXHAUSTED
                    result.stop_detail = (
                        f"No candidates left: {result.accepted} of {target} items accepted. "
                        "Relax the conditions to find more."
                    )
                    enter(S.ASSEMBLE)
                    result.state = S.DONE
                    return result

                guard()
                enter(S.DECIDE)
                tier = self.reasoner.generator_tier  # pass-through until the router (#165)
                result.tiers.append(tier)
                if (
                    keep_local
                    and self.reasoner.config.providers[
                        self.reasoner.config.tiers[tier].provider
                    ].cloud
                ):
                    return stop(
                        StopReason.DECLINED,
                        f"This brief is keep-local and the tier '{tier}' is a cloud tier. "
                        "The brief was not sent anywhere.",
                    )

                before = result.accepted
                outcome = self.reasoner.run(
                    brief=brief,
                    records=candidates,
                    keep_local=keep_local,
                    cap_usd=cap_usd - result.spent_usd,  # one cap for the whole board
                    on_phase=lambda phase: enter(S.GENERATE if phase == "generate" else S.VERIFY),
                    before_call=guard,
                )
                result.records += candidates
                result.items.update(outcome.items)
                result.spent_usd += outcome.spent_usd
                result.sent_to += [p for p in outcome.sent_to if p not in result.sent_to]
                result.models_used.update(outcome.models_used)
                if outcome.stop is not None:
                    return stop(outcome.stop, outcome.stop_detail or outcome.stop.banner)

                if result.accepted >= target:
                    enter(S.ASSEMBLE)
                    result.state = S.DONE
                    return result
                no_progress = no_progress + 1 if result.accepted == before else 0
                if no_progress >= self.config.stuck_rounds:
                    return stop(
                        StopReason.NO_PROGRESS,
                        f"No new accepted item in {no_progress} rounds in a row; "
                        f"{result.accepted} of {target} items accepted.",
                    )
        except Interrupted as interrupted:
            return stop(interrupted.reason, interrupted.detail)
