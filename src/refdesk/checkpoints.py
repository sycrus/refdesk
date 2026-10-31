"""Checkpoint and resume: a killed run continues from its completed steps (issue #157;
PRD 10.2, acceptance scenario 3).

What it does: every completed step of a run writes its result into the run store's
`checkpoints` table, keyed by the idempotency key (run ID, step, hash of inputs) — the
same redacted `args_hash` the run log uses, so a checkpoint cross-references its call
event. Three kinds of step are checkpointed:

- `retrieve`: the one ranked search for the brief, so a resumed run ranks the same
  candidates in the same order and re-derives the same rounds;
- `llm`: each completed (HTTP 200) model answer, through `CheckpointTransport`, which
  the board puts between the reasoner and the real transport. A reused answer reaches
  `LLMClient` as a normal answer marked `reused` (`llm.client.Answer`), so the budget
  is re-counted from its recorded usage — the cap still holds across a restart — but
  it is not logged as an attempt and never sent twice.
- `export`: the provenance pack, closing the crash window between writing the pack
  and saving the read-only board: a retry returns the recorded receipt and never
  writes the pack again.

Resume runs the same loop from Init; completed steps are answered from the store (each
reuse writes a `tool="checkpoint"` event instead of a second call event), so the
re-derived trajectory is identical to the original up to the kill, then the run
continues with live calls. Failed attempts (429, 5xx, timeouts) are never
checkpointed: a resumed run should re-ask a provider that may have recovered, and the
client's own retries replay those attempts live. Reused answers are exactly the
recorded ones; answers after the kill are whatever the provider returns now.

What breaks without it: a killed run would start over — repeating every model call and
paying for it twice — and could rank candidates into a different board.

`ResumeLog` is the run log of a resumed run. The loop re-derives the rounds the killed
process already logged, so a `retrieve` event that repeats one already in the file
(same arguments, same candidates) is written as a checkpoint event; the file then
holds each real call once, in order, and `replay` (runlog.py, issue #156) keeps
working on a resumed run's file.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from refdesk.llm.client import Answer, UrllibTransport
from refdesk.retrieval import Hit, Query
from refdesk.runlog import RunLog, args_hash, read_events

if TYPE_CHECKING:
    from refdesk.boards import RunStore
    from refdesk.llm.client import Transport

RETRIEVE_STEP = "retrieve"  # one ranked search for the brief
MODEL_STEP = "llm"  # one completed model answer
EXPORT_STEP = "export"  # the provenance pack write


class CheckpointTransport:
    """A `Transport` that answers completed model calls from the run store (issue #157).

    The first time a request is made it goes to `inner` and its 200 answer is
    checkpointed under the hash of (url, payload). On a later execution of the same
    run — a resume — the recorded answer comes back marked `reused`, so the client
    does not log it as an attempt and the provider is not asked twice. Each reuse is
    logged as a `checkpoint` call event with the same `args_hash` as the original.
    """

    def __init__(
        self,
        inner: Transport | None,
        *,
        store: RunStore,
        run_id: str,
        brief: str,
        log: RunLog | None = None,
    ):
        self.inner = inner or UrllibTransport()  # the reasoner's, or the client default
        self.store = store
        self.run_id = run_id
        self.brief = brief
        self.log = log
        self.hits = 0  # answers served from the store on this execution

    def post_json(self, url: str, headers: dict[str, str], payload: dict[str, Any]):
        key = args_hash({"url": url, "payload": payload}, self.brief)
        recorded = self.store.get_checkpoint(self.run_id, MODEL_STEP, key)
        if recorded is not None:
            self.hits += 1
            if self.log is not None:
                self.log.call(
                    "checkpoint", {"url": url, "payload": payload},
                    result=f"reused from checkpoint: HTTP {recorded['status']}",
                )  # fmt: skip
            return Answer(recorded["status"], recorded["body"], reused=True)
        status, body = self.inner.post_json(url, headers, payload)
        if status == 200:
            self.store.put_checkpoint(
                self.run_id, MODEL_STEP, key, {"status": status, "body": body}
            )
        return Answer(status, body)


def _hit_json(hit: Hit) -> dict[str, Any]:
    return {
        "record_id": hit.record_id,
        "score": hit.score,
        "matched": list(hit.matched),
        "union_size": hit.union_size,
        "components": [list(part) for part in hit.components],
    }


def checkpointed_search(
    store: RunStore,
    run_id: str,
    brief: str,
    query: Query,
    search: Callable[[], list[Hit]],
) -> list[Hit]:
    """The ranked hits for `query`, from the checkpoint when already recorded — a
    resumed run must rank the same candidates, or it would re-derive different rounds
    — otherwise a live search that is then checkpointed. The search itself is logged
    by the loop as the rounds hand candidates out; a reused search shows as those
    re-derived `retrieve` events becoming checkpoint events (`ResumeLog`)."""
    key = args_hash({"query": asdict(query)}, brief)
    recorded = store.get_checkpoint(run_id, RETRIEVE_STEP, key)
    if recorded is not None:
        return [
            Hit(
                record_id=h["record_id"], score=h["score"], matched=tuple(h["matched"]),
                union_size=h["union_size"], components=tuple(map(tuple, h["components"])),
            )  # fmt: skip
            for h in recorded["hits"]
        ]
    hits = search()
    store.put_checkpoint(run_id, RETRIEVE_STEP, key, {"hits": [_hit_json(h) for h in hits]})
    return hits


class ResumeLog(RunLog):
    """The run log of a resumed run (issue #157).

    The loop re-derives the rounds the killed process already logged. A `retrieve`
    event that repeats one already in the file (same arguments hash, same candidate
    IDs) is a re-derivation, not a call: it is written as a `checkpoint` event, so
    the file holds each real call once, in order, and replay keeps working. A fresh
    run never triggers this — two rounds can ask for the same n, but never hand out
    the same candidates twice."""

    def __init__(self, path: str | Any, *, run_id: str, brief: str):
        super().__init__(path, run_id=run_id, brief=brief)
        self._recorded: set[tuple[str, tuple[str, ...]]] = {
            (
                e.args_hash or "",
                tuple(r["id"] for r in (e.recorded or {}).get("records", [])),
            )  # fmt: skip
            for e in read_events(path)
            if e.tool == "retrieve"
        }

    def retrieval(self, n: int, records: list, latency_s: float):
        key = (args_hash({"n": n}, self.brief), tuple(r.id for r in records))
        if key in self._recorded:
            return self.call(
                "checkpoint", {"n": n},
                result=f"reused from checkpoint: {len(records)} candidates",
            )  # fmt: skip
        event = super().retrieval(n, records, latency_s)
        self._recorded.add(key)
        return event
