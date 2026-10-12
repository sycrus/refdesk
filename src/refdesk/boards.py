"""Retrieval-only boards behind POST /boards and GET /runs/{id} (issue #45).

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

import sqlite3
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from refdesk.api.models import (
    BoardItem,
    BoardRequest,
    Cost,
    Evidence,
    Gate,
    GateId,
    GateState,
    LoopState,
    RunView,
)
from refdesk.retrieval import Hit, Query, Retriever
from refdesk.retrieval.metadata import _phrase
from refdesk.schema import ArtworkRecord
from refdesk.wording import AttributionStatus, StopReason

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


def _view(
    run_id: str,
    request: BoardRequest,
    state: LoopState,
    items: list[BoardItem] = (),  # type: ignore[assignment]
    stop: StopReason | None = None,
    detail: str | None = None,
) -> RunView:
    return RunView(
        run_id=run_id,
        request=request,
        state=state,
        stop_reason=stop,
        stop_banner=stop.banner if stop else None,
        stop_detail=detail,
        gates=_gates(state, len(items), request.budget_cap_usd),
        items=list(items),
        cost=Cost(spent_usd=0.0, cap_usd=request.budget_cap_usd),
        keep_local=request.keep_local,
        sent_to=[],  # retrieval only: no brief is sent to any model
    )


class UnknownAnchor(KeyError):
    pass


class BoardService:
    def __init__(
        self,
        runs: RunStore,
        load_records: Callable[[], list[ArtworkRecord]],
        build_retriever: Callable[[list[ArtworkRecord]], Retriever],
        retriever_name: str,
    ):
        self.runs = runs
        self._load_records = load_records
        self._build = build_retriever
        self.retriever_name = retriever_name
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
        hits = retriever.search(to_query(request))
        items = [
            self._item(hit, records[hit.record_id]) for hit in hits if hit.record_id in records
        ]
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


def default_service(db_path: str | Path = "data/refdesk.sqlite") -> BoardService:
    """The service the API uses: records from the store, the retriever named in
    config/retrieval.yaml (`api.retriever`), runs in the same SQLite file.

    REFDESK_RETRIEVER overrides the configured name. The browser tests use it to run
    `jaccard` where CLIP cannot load (CI has no torch). It still never falls back."""
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

    return BoardService(
        RunStore(db_path), load_records, lambda records: build_retriever(name, records), name
    )
