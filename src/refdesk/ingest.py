"""Resumable, idempotent ingest from a source adapter into the store (issue #8).

Resumable: object IDs already in `ingest_progress` are skipped, so a run that stops
(rate limit, network, Ctrl+C) continues where it left off. Idempotent: records are
upserted, so `refresh=True` re-fetches everything without creating duplicates.
`recheck_skipped=True` re-fetches only objects skipped for a classification that the
source now includes, after the slice is widened.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from refdesk.sources.met import SOURCE, Fetched, MetSource, to_record
from refdesk.store import Store


@dataclass
class IngestResult:
    listed: int = 0
    already_done: int = 0
    ingested: int = 0
    skipped: dict[str, int] = field(default_factory=dict)


def ingest(
    store: Store,
    source: MetSource,
    *,
    object_ids: list[int] | None = None,
    refresh: bool = False,
    recheck_skipped: bool = False,
    limit: int | None = None,
) -> IngestResult:
    ids = source.list_object_ids() if object_ids is None else object_ids
    done = set() if refresh else store.handled_object_ids(SOURCE)
    if recheck_skipped:
        # Re-fetch objects skipped for a classification the source now includes.
        reasons = {f"skipped:classification:{c}" for c in source.classifications}
        done -= store.object_ids_with_outcome(SOURCE, reasons)
    pending = [i for i in ids if str(i) not in done]
    result = IngestResult(listed=len(ids), already_done=len(ids) - len(pending))

    for object_id in pending[:limit]:
        outcome = source.fetch_one(object_id)  # MetUnavailable propagates: progress is kept
        if isinstance(outcome, Fetched):
            store.save(outcome.record, outcome.raw)
            result.ingested += 1
        else:
            store.mark_skipped(SOURCE, str(object_id), outcome.reason)
            result.skipped[outcome.reason] = result.skipped.get(outcome.reason, 0) + 1
    return result


@dataclass
class RebuildResult:
    rebuilt: int = 0
    missing_raw: list[str] = field(default_factory=list)


def rebuild(store: Store, source: str) -> RebuildResult:
    """Re-derive every record from its stored raw response, with no network calls.

    Use after the adapter's mapping changes. Rights keep their original `checked_at`,
    because a rebuild re-reads what the source said then; it does not re-check rights.
    """
    result = RebuildResult()
    for old in list(store.iter_records(source)):
        raw = store.get_raw(old.raw_record_ref)
        if raw is None:
            result.missing_raw.append(old.id)
            continue
        store.save(to_record(raw, checked_at=old.rights.checked_at), raw)
        result.rebuilt += 1
    return result
