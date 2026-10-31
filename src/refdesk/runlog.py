"""Run log: an append-only `events.jsonl` per run, briefs redacted (issue #156; PRD 10.2,
13A).

What it does: the loop controller writes one **transition** event every time it enters a
state, and one **call** event for every tool call inside a step: each retrieval, and each
model request attempt (through `LLMClient.observe`). An event holds the PRD 10.2 fields:
run ID, step, state, tool, hash of arguments, result summary, tokens, cost, latency,
model and adapter versions, decision probabilities and reason code. Call events also
hold the tool's **recorded output** (the candidate records, or the provider's raw
answer), so `replay` can run the same loop again with the recordings standing in for the
retriever and the model, and give the same items and stop reason without the original
services. A replayed request whose arguments differ from the recording stops with
`ReplayDiverged`, naming the step: that is how a faulty step is found.

Redaction (PRD 13A: briefs may be confidential): every string in an event is scrubbed
before it is written, so the brief never reaches the file, even inside an error message
or a model answer that quotes it. The arguments are hashed *after* redaction, so the hash
cannot be used to guess a short brief. Replay needs the brief from the operator (or the
run store) to put it back into recordings and to rebuild matching hashes; a wrong brief
diverges at the first model call.

Known limits: redaction matches the whole brief (any case, any whitespace, JSON-escaped,
or cut off at the end of a string), not single words or paraphrases of it. A recording
that quoted the brief in another case is restored in the brief's own case.

What breaks without it: a stopped or failed run leaves only its final view, so nobody can
see which step went wrong or rerun it; and there is no trace view until Phoenix (M5-06).

The file is the record; GET /runs/{id} shows the events without the recordings.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from refdesk.api.models import EventKind, LoopState, RunEvent
from refdesk.llm.client import CallObservation, ProviderTimeout
from refdesk.schema import ArtworkRecord
from refdesk.wording import StopReason

if TYPE_CHECKING:
    from refdesk.loop import LoopResult
    from refdesk.reasoning import Reasoner

REDACTED = "[brief redacted]"
MIN_CUT_PREFIX = 16  # a brief cut off at the end of a string is redacted from this length
FILENAME = "events.jsonl"


# --- Redaction ---


def _patterns(brief: str) -> list[re.Pattern[str]]:
    words = brief.split()
    if not words:
        return []
    flexible = r"\s+".join(re.escape(w) for w in words)
    escaped = json.dumps(brief, ensure_ascii=False)[1:-1]
    patterns = [re.compile(flexible, re.IGNORECASE)]
    if escaped != brief:
        patterns.append(re.compile(re.escape(escaped), re.IGNORECASE))
    return patterns


def _redact_text(text: str, brief: str, patterns: list[re.Pattern[str]]) -> str:
    for pattern in patterns:
        text = pattern.sub(REDACTED, text)
    # Error messages are often truncated (the client keeps 200 characters of a body), so
    # a brief cut off at the very end of a string is redacted too.
    lowered, cut = text.casefold(), brief.casefold()
    for n in range(len(cut) - 1, MIN_CUT_PREFIX - 1, -1):
        if lowered.endswith(cut[:n]):
            return text[: len(text) - n] + REDACTED
    return text


def redact(value: Any, brief: str) -> Any:
    """`value` with every occurrence of the brief replaced by REDACTED, in every string of
    nested dicts and lists (keys too)."""
    patterns = _patterns(brief)
    if not patterns:
        return value

    def walk(v: Any) -> Any:
        if isinstance(v, str):
            return _redact_text(v, brief, patterns)
        if isinstance(v, dict):
            return {walk(k): walk(x) for k, x in v.items()}
        if isinstance(v, list | tuple):
            return [walk(x) for x in v]
        return v

    return walk(value)


def restore(value: Any, brief: str) -> Any:
    """The inverse used by replay: REDACTED back to the brief."""
    if isinstance(value, str):
        return value.replace(REDACTED, brief)
    if isinstance(value, dict):
        return {restore(k, brief): restore(x, brief) for k, x in value.items()}
    if isinstance(value, list):
        return [restore(x, brief) for x in value]
    return value


def args_hash(args: Any, brief: str) -> str:
    """SHA-256 of the arguments as canonical JSON, after redaction."""
    canonical = json.dumps(redact(args, brief), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- Writing ---


def read_events(path: str | Path) -> list[RunEvent]:
    path = Path(path)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [RunEvent.model_validate_json(line) for line in lines if line.strip()]


class RunLog:
    """Appends events for one run. Opening an existing file continues its numbering; it
    never rewrites a line."""

    def __init__(self, path: str | Path, *, run_id: str, brief: str):
        self.path = Path(path)
        self.run_id = run_id
        self.brief = brief
        existing = read_events(self.path)
        self.seq = existing[-1].seq if existing else 0
        self.step = existing[-1].step if existing else 0
        self.state = existing[-1].state if existing else LoopState.INIT
        self.round = existing[-1].round if existing else 0

    def _write(self, kind: EventKind, **fields: Any) -> RunEvent:
        self.seq += 1
        event = RunEvent(
            seq=self.seq, run_id=self.run_id, at=datetime.now(UTC), step=self.step, kind=kind,
            state=self.state, round=self.round, **fields,
        )  # fmt: skip
        data = redact(event.model_dump(mode="json"), self.brief)
        line = json.dumps(data, ensure_ascii=False)
        for pattern in _patterns(self.brief):  # belt and braces: the serialised line too
            line = pattern.sub(REDACTED, line)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        return RunEvent.model_validate(data)

    def transition(self, state: LoopState, *, round: int | None = None, **fields: Any) -> RunEvent:
        """One event per state entered."""
        self.step += 1
        self.state = state
        if round is not None:
            self.round = round
        return self._write(EventKind.TRANSITION, **fields)

    def call(self, tool: str, args: Any, **fields: Any) -> RunEvent:
        """One event per tool call inside the current step."""
        return self._write(
            EventKind.CALL, tool=tool, args_hash=args_hash(args, self.brief), **fields
        )

    def retrieval(self, n: int, records: list[ArtworkRecord], latency_s: float) -> RunEvent:
        ids = ", ".join(r.id for r in records)
        return self.call(
            "retrieve", {"n": n}, latency_s=latency_s,
            result=f"{len(records)} candidates: {ids}" if records else "0 candidates",
            recorded={"records": [r.model_dump(mode="json") for r in records]},
        )  # fmt: skip

    def model_call(self, observation: CallObservation) -> RunEvent:
        """Used as `LLMClient.observe`: one event per request attempt."""
        o, c = observation, observation.completion
        body = o.body if isinstance(o.body, dict) else {}
        usage = body.get("usage") or {}
        result = "timeout" if o.status is None else f"HTTP {o.status}"
        if o.status is not None and o.status != 200:
            result += f": {str(o.body)[:200]}"
        return self.call(
            f"llm:{o.tier}", {"url": o.url, "payload": o.payload},
            result=result,
            tokens_in=c.tokens_in if c else usage.get("prompt_tokens"),
            tokens_out=c.tokens_out if c else usage.get("completion_tokens"),
            cost_usd=c.cost_usd if c else 0.0,
            latency_s=o.latency_s,
            model=(c.model_reported if c else body.get("model")) or o.payload.get("model"),
            recorded={"status": o.status, "body": o.body},
        )  # fmt: skip


# --- Replay ---


class ReplayDiverged(RuntimeError):
    """The replayed run asked for something the recording does not hold."""


class _Recordings:
    def __init__(self, events: list[RunEvent], brief: str):
        self.brief = brief
        self.retrievals = [e for e in events if e.tool == "retrieve"]
        self.model_calls = [e for e in events if e.tool and e.tool.startswith("llm:")]

    @staticmethod
    def _next(queue: list[RunEvent], what: str) -> RunEvent:
        if not queue:
            raise ReplayDiverged(f"the replay made a {what} the recording does not have")
        return queue.pop(0)

    def retrieve(self, n: int) -> list[ArtworkRecord]:
        event = self._next(self.retrievals, "retrieval")
        if args_hash({"n": n}, self.brief) != event.args_hash:
            raise ReplayDiverged(
                f"step {event.step} ({event.state}, retrieve): asked for {n} candidates, "
                "which differs from the recording"
            )
        records = restore(event.recorded["records"], self.brief)
        return [ArtworkRecord.model_validate(r) for r in records]

    def post_json(self, url: str, headers: dict[str, str], payload: dict[str, Any]):
        """The Transport the replayed LLMClient talks to. Never touches the network."""
        event = self._next(self.model_calls, "model request")
        if args_hash({"url": url, "payload": payload}, self.brief) != event.args_hash:
            raise ReplayDiverged(
                f"step {event.step} ({event.state}, {event.tool}): the request differs from "
                "the recording"
            )
        if event.recorded["status"] is None:
            raise ProviderTimeout(f"timeout (recorded): {url}")
        return event.recorded["status"], restore(event.recorded["body"], self.brief)


def replay(
    path: str | Path,
    *,
    brief: str,
    make_reasoner: Callable[[Any], Reasoner],
) -> LoopResult:
    """Run the recorded loop again with recordings for the retriever and the model.

    `make_reasoner(transport)` builds the Reasoner as the original run had it (tiers,
    prompts, keys and approval stay the caller's decision); its transport is the
    recording, so no request leaves the process. The kill switch and wall clock fire at
    the same guard check as in the recording."""
    from refdesk.loop import LoopConfig, LoopController

    events = read_events(path)
    if not events or events[0].state is not LoopState.INIT:
        raise ReplayDiverged(f"{path} does not start with an Init event")
    params = events[0].data
    recordings = _Recordings(events, brief)
    stops = [
        e for e in events
        if e.kind is EventKind.TRANSITION and e.state in (LoopState.STOPPED, LoopState.CANCELLED)
    ]  # fmt: skip
    stopped = stops[-1] if stops else None
    reason = stopped.reason_code if stopped else None
    at = stopped.data.get("guard_check") if stopped else None
    elapsed = float(stopped.data.get("elapsed_s", 0.0)) if stopped else 0.0
    checks = [0]

    def cancelled() -> bool:
        checks[0] += 1
        return reason == StopReason.CANCELLED.value and checks[0] == at

    def clock() -> float:
        return elapsed if reason == StopReason.TIMEOUT.value and checks[0] == at else 0.0

    controller = LoopController(
        LoopConfig(**params["loop"]), make_reasoner(recordings), clock=clock, cancelled=cancelled
    )
    return controller.run(
        brief=brief, retrieve=recordings.retrieve, target=params["target"],
        keep_local=params["keep_local"], cap_usd=params["cap_usd"],
    )  # fmt: skip
