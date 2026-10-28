"""Boards behind POST /boards and GET /runs/{id} (issues #45, #98).

With a `Reasoner` (issue #98), each item also gets a rationale, code checks and a judge
verdict (`reasoning.py`): the run moves retrieve, generate, verify; G1 shows the spend
against the cap and G2 the verification result; an item is "Attribution verified from
record" only when both checks pass. Without one, runs are retrieval-only, as below.

A board request becomes a retrieval `Query`; the configured retriever ranks records; each
hit becomes a board item with its evidence (record fields, with the record's own values),
its rights record and its score breakdown. There are no rationales and no verifier yet
(M3), so every attribution is "Needs human check" and the G0 and G2 checks show as
skipped, never as passed (PRD 8B rule 2). Nothing is sent to any model: cost is 0 and
`sent_to` is empty.

The search runs after POST returns (a FastAPI background task), so GET shows the state
moving from "retrieve" to "done" or "stopped". Runs are stored in a `runs` table, one
connection per call, because the background task runs on another thread and SQLite
connections cannot cross threads.

If the retriever cannot load (no torch, no index), the run stops with "source
unavailable" and `stop_detail` says what is missing. It never falls back to another
retriever silently.
"""

from __future__ import annotations

import csv
import os
import sqlite3
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from refdesk.api.models import (
    Approval,
    ApprovalRequest,
    BoardItem,
    BoardRequest,
    Cost,
    ErrorReport,
    Evidence,
    ExportReceipt,
    ExportRequest,
    Gate,
    GateId,
    GateState,
    ItemReview,
    LoopState,
    QueuedReport,
    ReviewRequest,
    RunView,
)
from refdesk.rationale import field_value
from refdesk.reasoning import ItemReasoning, Reasoner, ReasoningOutcome
from refdesk.retrieval import Hit, Query, Retriever
from refdesk.retrieval.combined import ConditionNotUnderstood
from refdesk.retrieval.metadata import _phrase
from refdesk.schema import ArtworkRecord, RightsStatus
from refdesk.verifier import _norm, item_status
from refdesk.wording import (
    EXPORTED,
    NOT_LEGAL_ADVICE,
    OPINION_FLAGGED,
    AttributionStatus,
    StopReason,
)

NO_VERIFIER = "No verifier yet (M3): the attribution has not been checked against the record."
# Which score a single-signal retriever's number is, so every item explains its score.
SIGNAL = {"jaccard": "attributes", "clip": "similarity"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    request TEXT NOT NULL,
    view TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    reported_at TEXT NOT NULL,
    report TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class RunStore:
    """Run state in SQLite. One connection per call (see the module note on threads)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def save(self, view: RunView, request: BoardRequest | None = None) -> None:
        now = _now()
        with self._connect() as db:
            if request is None:
                db.execute(
                    "UPDATE runs SET view = ?, updated_at = ? WHERE run_id = ?",
                    (view.model_dump_json(), now, view.run_id),
                )
            else:
                db.execute(
                    "INSERT INTO runs (run_id, created_at, updated_at, request, view) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (view.run_id, now, now, request.model_dump_json(), view.model_dump_json()),
                )

    def get(self, run_id: str) -> RunView | None:
        with self._connect() as db:
            row = db.execute("SELECT view FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return RunView.model_validate_json(row[0]) if row else None

    def add_report(self, report: QueuedReport) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO reports (report_id, reported_at, report) VALUES (?, ?, ?)",
                (report.report_id, report.reported_at.isoformat(), report.model_dump_json()),
            )

    def reports(self) -> list[QueuedReport]:
        with self._connect() as db:
            rows = db.execute("SELECT report FROM reports ORDER BY rowid").fetchall()
        return [QueuedReport.model_validate_json(r[0]) for r in rows]


def to_query(request: BoardRequest) -> Query:
    conditions = {k: v for k, v in request.conditions.model_dump().items() if v}
    return Query(
        brief=request.brief,
        conditions=conditions,
        anchor_id=request.anchor_id,
        avoid=list(request.avoid),
        k=request.target_items,
        usage_mode=request.usage_mode.value,
    )


def evidence_for(hit: Hit, record: ArtworkRecord) -> list[Evidence]:
    """Turn matched attributes ("tag:boat", "century:17", "filter:medium:oil") into record
    fields with the record's own values ("subject_tags": "Boats", "date": "1650").
    Similarity is not a record field; it is in the score breakdown instead."""
    found: dict[tuple[str, str], Evidence] = {}

    def add(field: str, value: str | None) -> None:
        if value:
            found.setdefault(
                (field, value), Evidence(field=field, value=value, record_url=record.record_url)
            )

    for token in hit.matched:
        namespace, _, value = token.removeprefix("filter:").partition(":")
        if namespace == "tag":
            for tag in record.subject_tags:
                if _phrase(tag) == value:
                    add("subject_tags", tag)
        elif namespace == "medium":
            add("medium", record.medium)
        elif namespace == "artist":
            add("artist", record.artist)
        elif namespace == "classification":
            add("classification", record.classification)
        elif namespace == "century":
            add("date", record.date or (str(record.date_begin) if record.date_begin else None))
    return list(found.values())


def _reasoned_gates(
    state: LoopState, items: list[BoardItem], cap: float, outcome: ReasoningOutcome | None
) -> list[Gate]:
    """Gates once a Reasoner runs: G1 is the real spend, G2 the verification result."""
    done = state in (LoopState.DONE, LoopState.STOPPED)
    spent = outcome.spent_usd if outcome else 0.0
    if outcome and outcome.stop is StopReason.BUDGET_CAP:
        spend = Gate(
            id=GateId.G1_SPEND,
            state=GateState.BLOCKED,
            status_text=f"Budget cap reached: USD {spent:.3f} of {cap:.3f}.",
            actor="operator",
        )
    else:
        spend = Gate(
            id=GateId.G1_SPEND,
            state=GateState.PASSED if done else GateState.ACTIVE,
            status_text=f"USD {spent:.3f} of {cap:.3f}.",
        )
    flagged = sum(1 for i in items if i.attribution_status is not AttributionStatus.VERIFIED)
    if not done:
        verify = Gate(
            id=GateId.G2_VERIFY,
            state=GateState.ACTIVE if state is LoopState.VERIFY else GateState.PENDING,
            status_text="Checking every claim against its record.",
        )
        review = Gate(
            id=GateId.G3_REVIEW,
            state=GateState.PENDING,
            status_text="Nothing to review yet.",
            actor="operator",
        )
    else:
        if items and not flagged:
            verify = Gate(
                id=GateId.G2_VERIFY,
                state=GateState.PASSED,
                status_text=f"All {len(items)} items verified against their records.",
            )
        else:
            verify = Gate(
                id=GateId.G2_VERIFY,
                state=GateState.BLOCKED,
                status_text=f"{flagged} of {len(items)} items need a human check: see each card.",
            )
        if flagged:
            review = Gate(
                id=GateId.G3_REVIEW,
                state=GateState.ACTIVE,
                status_text=f"{flagged} items need a human check.",
                actor="operator",
            )
        else:
            review = Gate(
                id=GateId.G3_REVIEW,
                state=GateState.SKIPPED,
                status_text="No flagged items.",
                actor="operator",
            )
    return [
        Gate(id=GateId.G0_INTAKE, state=GateState.SKIPPED, status_text="No intake checks yet."),
        spend,
        verify,
        review,
        Gate(
            id=GateId.G4_APPROVE,
            state=GateState.PENDING,
            status_text="Waiting for review.",
            actor="approver",
        ),
        Gate(
            id=GateId.G5_EXPORT,
            state=GateState.PENDING,
            status_text="Not exported.",
            actor="approver",
        ),
    ]


def _gates(state: LoopState, items: int, cap: float) -> list[Gate]:
    done = state in (LoopState.DONE, LoopState.STOPPED)
    spend = (
        Gate(
            id=GateId.G1_SPEND,
            state=GateState.PASSED,
            status_text=f"No paid calls: USD 0.000 of {cap:.3f}.",
        )
        if done
        else Gate(
            id=GateId.G1_SPEND, state=GateState.ACTIVE, status_text=f"USD 0.000 of {cap:.3f}."
        )
    )
    if state is LoopState.DONE and items:
        review = Gate(
            id=GateId.G3_REVIEW,
            state=GateState.ACTIVE,
            status_text=f"{items} items need a human check (no verifier yet).",
            actor="operator",
        )
    else:
        review = Gate(
            id=GateId.G3_REVIEW,
            state=GateState.PENDING,
            status_text="Nothing to review yet.",
            actor="operator",
        )
    return [
        Gate(id=GateId.G0_INTAKE, state=GateState.SKIPPED, status_text="No intake checks yet."),
        spend,
        Gate(
            id=GateId.G2_VERIFY,
            state=GateState.SKIPPED,
            status_text="No verifier yet (M3): every attribution needs a human check.",
        ),
        review,
        Gate(
            id=GateId.G4_APPROVE,
            state=GateState.PENDING,
            status_text="Waiting for review.",
            actor="approver",
        ),
        Gate(
            id=GateId.G5_EXPORT,
            state=GateState.PENDING,
            status_text="Not exported.",
            actor="approver",
        ),
    ]


def review_gates(gates: list[Gate], items: list[BoardItem], ended: bool) -> list[Gate]:
    """G3 and G4 from the items' review decisions (issue #100). Approval (G4) opens only
    when every flagged item is decided; the API enforces it at approval too (#101)."""
    if not ended or not items:
        return gates
    flagged = [i for i in items if i.attribution_status is not AttributionStatus.VERIFIED]
    decided = [i for i in flagged if i.review is not None]
    by_id = {g.id: g for g in gates}
    g3, g4 = by_id[GateId.G3_REVIEW], by_id[GateId.G4_APPROVE]
    ready = Gate(
        id=GateId.G4_APPROVE,
        state=GateState.ACTIVE,
        status_text="Ready for approval.",
        actor="approver",
    )
    if not flagged:
        g4 = ready
    elif len(decided) == len(flagged):
        kept = sum(1 for i in decided if i.review.decision == "keep")
        g3 = Gate(
            id=GateId.G3_REVIEW,
            state=GateState.PASSED,
            status_text=(
                f"All {len(flagged)} flagged items decided: "
                f"{kept} kept, {len(flagged) - kept} dropped."
            ),
            actor="operator",
        )
        g4 = ready
    elif decided:
        g3 = Gate(
            id=GateId.G3_REVIEW,
            state=GateState.ACTIVE,
            status_text=f"{len(decided)} of {len(flagged)} flagged items decided.",
            actor="operator",
        )
        g4 = Gate(
            id=GateId.G4_APPROVE,
            state=GateState.PENDING,
            status_text=(
                f"Waiting for review: {len(flagged) - len(decided)} flagged items still need "
                "a decision."
            ),
            actor="approver",
        )
    return [
        g3 if g.id == GateId.G3_REVIEW else g4 if g.id == GateId.G4_APPROVE else g for g in gates
    ]


def _view(
    run_id: str,
    request: BoardRequest,
    state: LoopState,
    items: list[BoardItem] = (),  # type: ignore[assignment]
    stop: StopReason | None = None,
    detail: str | None = None,
    outcome: ReasoningOutcome | None = None,
    reasoned: bool = False,
) -> RunView:
    if reasoned:
        gates = _reasoned_gates(state, list(items), request.budget_cap_usd, outcome)
    else:
        gates = _gates(state, len(items), request.budget_cap_usd)
    gates = review_gates(gates, list(items), state in (LoopState.DONE, LoopState.STOPPED))
    return RunView(
        run_id=run_id,
        request=request,
        state=state,
        stop_reason=stop,
        stop_banner=stop.banner if stop else None,
        stop_detail=detail,
        gates=gates,
        items=list(items),
        cost=Cost(spent_usd=outcome.spent_usd if outcome else 0.0, cap_usd=request.budget_cap_usd),
        keep_local=request.keep_local,
        sent_to=list(outcome.sent_to) if outcome else [],  # empty: retrieval only
        models_used=dict(outcome.models_used) if outcome else {},
    )


PACK_COLUMNS = (
    "run_id", "item_id", "title", "artist", "date", "source", "object_id", "record_url",
    "usage_mode", "rights_status", "flag_field", "flag_value", "licence_string", "credit_line",
    "checked_at", "attribution_status", "review_decision", "review_note", "reviewed_by",
    "rationale", "opinion_flag", "tier_used", "generator_model", "judge_model", "retriever",
    "approver",
    "approved_at", "exported_at", "not_legal_advice",
)  # fmt: skip


def pack_items(items: list[BoardItem]) -> tuple[list[BoardItem], int, int]:
    """What the provenance pack holds (rights-check skill): verified items and items kept at
    review. Left out: dropped items, and items whose rights are unverified unless someone
    reviewed and kept them. Returns (included, excluded unverified, dropped)."""
    included, unverified, dropped = [], 0, 0
    for item in items:
        if item.review is not None and item.review.decision == "drop":
            dropped += 1
        elif item.record.rights.status is RightsStatus.UNVERIFIED and not (
            item.review and item.review.decision == "keep"
        ):
            unverified += 1
        elif item.attribution_status is AttributionStatus.VERIFIED or (
            item.review and item.review.decision == "keep"
        ):
            included.append(item)
    return included, unverified, dropped


def _git_sha() -> str:
    import subprocess

    try:
        return subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


class UnknownAnchor(KeyError):
    pass


class UnknownRun(KeyError):
    pass


class UnknownItem(KeyError):
    pass


def _with_gate(gates: list[Gate], gate: Gate) -> list[Gate]:
    """The gates with one replaced by its new state."""
    return [gate if g.id == gate.id else g for g in gates]


class FormatNotSupported(ValueError):
    pass


class ExportFailed(RuntimeError):
    """Writing the pack failed; the board stays unlocked."""


class GateRefused(Exception):
    """A gate's rule refused the request; the API answers 409 with the gate and reason."""

    def __init__(self, gate: GateId, reason: str):
        super().__init__(reason)
        self.gate = gate
        self.reason = reason


class BoardService:
    def __init__(
        self,
        runs: RunStore,
        load_records: Callable[[], list[ArtworkRecord]],
        build_retriever: Callable[[list[ArtworkRecord]], Retriever],
        retriever_name: str,
        check_conditions: Callable[[dict[str, str]], None] | None = None,
        reasoner: Reasoner | None = None,
    ):
        self.runs = runs
        self._load_records = load_records
        self._build = build_retriever
        self.retriever_name = retriever_name
        # Refuses conditions the retriever cannot apply (issue #63), before anything loads.
        self._check_conditions = check_conditions
        self.reasoner = reasoner  # None: retrieval-only boards
        self.exports_dir = Path("runs/exports")  # provenance packs (gitignored)
        self._records: dict[str, ArtworkRecord] | None = None
        self._retriever: Retriever | None = None
        self._lock = threading.Lock()  # load the records and retriever once

    def records(self) -> dict[str, ArtworkRecord]:
        with self._lock:
            if self._records is None:
                self._records = {r.id: r for r in self._load_records()}
            return self._records

    def retriever(self) -> Retriever:
        records = self.records()
        with self._lock:
            if self._retriever is None:
                self._retriever = self._build(list(records.values()))
            return self._retriever

    def create(self, request: BoardRequest) -> RunView:
        if request.anchor_id is not None and request.anchor_id not in self.records():
            raise UnknownAnchor(request.anchor_id)
        if self._check_conditions is not None:
            self._check_conditions(to_query(request).conditions)  # ConditionNotUnderstood
        view = _view(f"run-{uuid.uuid4().hex[:12]}", request, LoopState.RETRIEVE)
        self.runs.save(view, request)
        return view

    def execute(self, run_id: str, request: BoardRequest) -> RunView:
        try:
            retriever = self.retriever()
        except Exception as error:  # noqa: BLE001 - any load failure stops the run, loudly
            detail = (
                f"Retriever '{self.retriever_name}' could not load: "
                f"{type(error).__name__}: {error}. No other retriever was used."
            )
            view = _view(
                run_id,
                request,
                LoopState.STOPPED,
                stop=StopReason.SOURCE_UNAVAILABLE,
                detail=detail,
            )
            self.runs.save(view)
            return view

        records = self.records()
        try:
            hits = retriever.search(to_query(request))
        except ConditionNotUnderstood as error:  # normally refused at create()
            view = _view(
                run_id, request, LoopState.STOPPED, stop=StopReason.DECLINED, detail=str(error)
            )
            self.runs.save(view)
            return view
        hits = [hit for hit in hits if hit.record_id in records]
        if hits and self.reasoner is not None:
            return self._execute_reasoned(run_id, request, hits, records)
        items = [self._item(hit, records[hit.record_id]) for hit in hits]
        if items:
            view = _view(run_id, request, LoopState.DONE, items)
        else:
            view = _view(
                run_id,
                request,
                LoopState.STOPPED,
                stop=StopReason.POOL_EXHAUSTED,
                detail="No record matched the brief, conditions and rights filter.",
            )
        self.runs.save(view)
        return view

    def _execute_reasoned(
        self, run_id: str, request: BoardRequest, hits: list[Hit], records: dict
    ) -> RunView:
        def phase(name: str) -> None:
            state = LoopState.GENERATE if name == "generate" else LoopState.VERIFY
            self.runs.save(_view(run_id, request, state, reasoned=True))

        chosen = [records[hit.record_id] for hit in hits]
        outcome = self.reasoner.run(
            brief=request.brief,
            records=chosen,
            keep_local=request.keep_local,
            cap_usd=request.budget_cap_usd,
            on_phase=phase,
        )
        items = [
            self._reasoned_item(hit, records[hit.record_id], outcome.items[hit.record_id])
            for hit in hits
        ]
        if outcome.stop is StopReason.DECLINED:
            items = []  # nothing was sent anywhere, so a declined request shows no board
        state = LoopState.STOPPED if outcome.stop else LoopState.DONE
        view = _view(
            run_id,
            request,
            state,
            items,
            stop=outcome.stop,
            detail=outcome.stop_detail,
            outcome=outcome,
            reasoned=True,
        )
        self.runs.save(view)
        return view

    def _reasoned_item(self, hit: Hit, record: ArtworkRecord, r: ItemReasoning) -> BoardItem:
        item = self._item(hit, record)
        evidence = list(item.evidence)
        seen = {(e.field, e.value) for e in evidence}
        reasons: list[str] = []
        rationale = None
        generated = r.generated
        if generated is not None and generated.ok:
            claims = generated.rationale.claims
            rationale = " ".join([*(c.text for c in claims), generated.rationale.fit])
            for check, claim in zip(r.code.checks, claims, strict=True):
                if check.status != "pass":
                    continue
                if claim.field == "subject_tags":
                    values = [t for t in record.subject_tags if _norm(t) == _norm(claim.value)]
                else:
                    values = [field_value(record, claim.field)]
                for value in values:
                    if value and (claim.field, value) not in seen:
                        seen.add((claim.field, value))
                        evidence.append(
                            Evidence(field=claim.field, value=value, record_url=record.record_url)
                        )
            reasons += list(r.code.failures)
        elif generated is not None:
            reasons.append(generated.failure)
        fit_failure = r.judged.verdict.fit_failure if r.judged is not None else None
        if r.judged is not None:
            reasons += list(r.judged.verdict.failures)
        if fit_failure:
            reasons.append(fit_failure)
        reasons += r.notes
        status = item_status(r.code, r.judged.verdict if r.judged else None)
        return item.model_copy(
            update={
                "rationale": rationale,
                "evidence": evidence,
                "attribution_status": status,
                "flag_reasons": [] if status is AttributionStatus.VERIFIED else reasons,
                "opinion_flag": OPINION_FLAGGED if fit_failure else None,
                "tier_used": generated.tier if generated else None,
                "cost_usd": r.cost_usd,
            }
        )

    def _item(self, hit: Hit, record: ArtworkRecord) -> BoardItem:
        components = dict(hit.components) or {SIGNAL.get(self.retriever_name, "score"): hit.score}
        return BoardItem(
            record=record,
            rationale=None,
            evidence=evidence_for(hit, record),
            attribution_status=AttributionStatus.NEEDS_HUMAN_CHECK,
            flag_reasons=[NO_VERIFIER],
            score=hit.score,
            score_components=components,
        )

    def get(self, run_id: str) -> RunView | None:
        return self.runs.get(run_id)

    def review(self, run_id: str, request: ReviewRequest) -> RunView:
        """G3: record keep (with a note) or drop for flagged items, with who and when."""
        view = self.runs.get(run_id)
        if view is None:
            raise UnknownRun(run_id)
        if view.read_only:
            raise GateRefused(GateId.G3_REVIEW, "the board is exported and read-only")
        if view.state not in (LoopState.DONE, LoopState.STOPPED):
            raise GateRefused(GateId.G3_REVIEW, "the run is still working")
        approval = next(g for g in view.gates if g.id == GateId.G4_APPROVE)
        if approval.state is GateState.PASSED:
            raise GateRefused(GateId.G3_REVIEW, "the board is already approved")
        items = {i.record.id: i for i in view.items}
        now = datetime.now(UTC)
        for d in request.decisions:
            if d.item_id not in items:
                raise UnknownItem(d.item_id)
            if items[d.item_id].attribution_status is AttributionStatus.VERIFIED:
                raise GateRefused(
                    GateId.G3_REVIEW, f"{d.item_id} is not flagged; only flagged items are reviewed"
                )
        for d in request.decisions:
            note = d.note.strip() if d.note else None
            review = ItemReview(
                decision=d.decision, note=note or None, decided_by=request.reviewer, decided_at=now
            )
            items[d.item_id] = items[d.item_id].model_copy(update={"review": review})
        new_items = [items[i.record.id] for i in view.items]
        updated = view.model_copy(
            update={"items": new_items, "gates": review_gates(view.gates, new_items, True)}
        )
        self.runs.save(updated)
        return updated

    def approve(self, run_id: str, request: ApprovalRequest) -> RunView:
        """G4: record approval. Refused until every flagged item is decided (G3)."""
        view = self.runs.get(run_id)
        if view is None:
            raise UnknownRun(run_id)
        g4 = GateId.G4_APPROVE
        if view.read_only:
            raise GateRefused(g4, "the board is exported and read-only")
        if view.approval is not None:
            raise GateRefused(g4, f"already approved by {view.approval.approver}")
        if view.state not in (LoopState.DONE, LoopState.STOPPED):
            raise GateRefused(g4, "the run is still working")
        undecided = [
            i for i in view.items
            if i.attribution_status is not AttributionStatus.VERIFIED and i.review is None
        ]  # fmt: skip
        if undecided:
            raise GateRefused(g4, f"{len(undecided)} flagged items still need a decision (G3)")
        included, _, _ = pack_items(view.items)
        if not included:
            raise GateRefused(g4, "nothing to approve: every item was dropped or excluded")
        approval = Approval(approver=request.approver, approved_at=datetime.now(UTC))
        approved = Gate(
            id=GateId.G4_APPROVE,
            state=GateState.PASSED,
            status_text=f"Approved by {approval.approver}.",
            actor="approver",
        )
        ready = Gate(
            id=GateId.G5_EXPORT,
            state=GateState.ACTIVE,
            status_text=f"Ready to export {len(included)} items.",
            actor="approver",
        )
        gates = _with_gate(_with_gate(view.gates, approved), ready)
        updated = view.model_copy(update={"approval": approval, "gates": gates})
        self.runs.save(updated)
        return updated

    def export(self, run_id: str, request: ExportRequest) -> ExportReceipt:
        """G5: write the provenance pack, then make the board read-only. Irreversible.

        The CSV is written to a temporary file and moved into place, so a failed export
        leaves no partial pack and the board stays unlocked (ExportFailed)."""
        view = self.runs.get(run_id)
        if view is None:
            raise UnknownRun(run_id)
        if view.read_only:
            raise GateRefused(GateId.G5_EXPORT, "already exported; the board is read-only")
        if view.approval is None:
            raise GateRefused(GateId.G5_EXPORT, "no approval record (G4)")
        if request.format != "csv":
            raise FormatNotSupported(request.format)
        included, _, _ = pack_items(view.items)
        exported_at = datetime.now(UTC)
        versions = {
            "generator": view.models_used.get("generator", "none"),
            "judge": view.models_used.get("judge", "none"),
            "retriever": self.retriever_name,
            "git": _git_sha(),
        }
        target = Path(self.exports_dir) / f"{run_id}.csv"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_suffix(".csv.partial")
            with partial.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=PACK_COLUMNS)
                writer.writeheader()
                for item in included:
                    writer.writerow(self._pack_row(view, item, versions, exported_at))
            os.replace(partial, target)
        except OSError as error:
            raise ExportFailed(f"{type(error).__name__}: {error}") from error
        receipt = ExportReceipt(
            run_id=run_id,
            file=target.as_posix(),
            exported_at=exported_at,
            approver=view.approval.approver,
            versions=versions,
            notice=EXPORTED,
            not_legal_advice=NOT_LEGAL_ADVICE,
        )
        exported = Gate(
            id=GateId.G5_EXPORT,
            state=GateState.PASSED,
            status_text=f"Exported {len(included)} items to {target.name}.",
            actor="approver",
        )
        gates = _with_gate(view.gates, exported)
        self.runs.save(
            view.model_copy(update={"read_only": True, "export": receipt, "gates": gates})
        )
        return receipt

    def _pack_row(self, view: RunView, item: BoardItem, versions: dict, exported_at) -> dict:
        record, rights, review = item.record, item.record.rights, item.review
        return {
            "run_id": view.run_id,
            "item_id": record.id,
            "title": record.title or "",
            "artist": record.artist or "",
            "date": record.date or "",
            "source": record.source,
            "object_id": record.object_id,
            "record_url": record.record_url or "",
            "usage_mode": view.request.usage_mode.value if view.request else "",
            "rights_status": rights.status.value,
            "flag_field": rights.flag_field or "",
            "flag_value": "" if rights.flag_value is None else str(rights.flag_value),
            "licence_string": rights.licence_string or "",
            "credit_line": record.credit_line or "",
            "checked_at": rights.checked_at.isoformat(),
            "attribution_status": item.attribution_status.value,
            "review_decision": review.decision if review else "",
            "review_note": (review.note or "") if review else "",
            "reviewed_by": review.decided_by if review else "",
            "rationale": item.rationale or "",
            "tier_used": item.tier_used or "",
            "generator_model": versions["generator"],
            "judge_model": versions["judge"],
            "retriever": versions["retriever"],
            "approver": view.approval.approver,
            "approved_at": view.approval.approved_at.isoformat(),
            "exported_at": exported_at.isoformat(),
            "not_legal_advice": NOT_LEGAL_ADVICE,
        }

    def report(self, request: ErrorReport) -> QueuedReport:
        """S8: queue one board item for human review, with who and when. The board is not
        changed, so an exported board can still be reported."""
        view = self.runs.get(request.run_id)
        if view is None:
            raise UnknownRun(request.run_id)
        if all(i.record.id != request.item_id for i in view.items):
            raise UnknownItem(request.item_id)
        queued = QueuedReport(
            report_id=f"report-{uuid.uuid4().hex[:12]}",
            run_id=request.run_id,
            item_id=request.item_id,
            error_type=request.error_type,
            note=request.note,
            reported_by=request.reporter,
            reported_at=datetime.now(UTC),
        )
        self.runs.add_report(queued)
        return queued

    def reports(self) -> list[QueuedReport]:
        """The S8 review queue, oldest first."""
        return self.runs.reports()


def default_service(db_path: str | Path = "data/refdesk.sqlite") -> BoardService:
    """The service the API uses: records from the store, the retriever named in
    config/retrieval.yaml (`api.retriever`), runs in the same SQLite file.

    REFDESK_RETRIEVER overrides the configured name. The browser tests use it to run
    `jaccard` where CLIP cannot load (CI has no torch). It still never falls back.

    Rationales come from `api.reasoning` (generator and judge tiers, issue #98).
    REFDESK_GENERATOR_TIER overrides the generator; "none" gives retrieval-only boards.
    Local models are loaded through the ModelManager, one per phase."""
    import os

    import yaml

    from refdesk.retrieval.registry import build_retriever
    from refdesk.store import Store

    config = yaml.safe_load(Path("config/retrieval.yaml").read_text(encoding="utf-8"))
    name = os.environ.get("REFDESK_RETRIEVER") or config["api"]["retriever"]

    def load_records() -> list[ArtworkRecord]:
        store = Store(db_path)
        try:
            return list(store.iter_records())
        finally:
            store.close()

    check = None
    if name == "combined":
        from refdesk.retrieval.combined import check_conditions, load_config

        combined_config = load_config()

        def check(conditions: dict[str, str]) -> None:
            check_conditions(conditions, combined_config)

    return BoardService(
        RunStore(db_path),
        load_records,
        lambda records: build_retriever(name, records),
        name,
        check,
        reasoner=default_reasoner(config.get("api", {}).get("reasoning") or {}),
    )


def default_reasoner(settings: dict) -> Reasoner | None:
    import os

    from refdesk.llm.config import ProvidersConfig
    from refdesk.llm.model_manager import ModelManager, OllamaBackend, load_specs

    tier = os.environ.get("REFDESK_GENERATOR_TIER") or settings.get("generator_tier")
    if not tier or tier == "none":
        return None
    specs = load_specs("config/models.yaml")
    manager = ModelManager(specs, {"ollama": OllamaBackend()})

    def ensure(model: str) -> None:
        if model in specs:  # GPU models only; the mock needs nothing
            manager.ensure(model)

    return Reasoner(
        ProvidersConfig.load("config/providers.yaml"),
        generator_tier=tier,
        judge_tier=settings.get("judge_tier", "auto"),
        ensure_model=ensure,
        prompts=settings.get("prompts"),
    )
