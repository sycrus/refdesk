"""Read operations behind GET /records/{id}, /records/{id}/rights, /records/{id}/image,
POST /search and POST /provenance (issue #200). The MCP server (#160) may wrap only these
and the other `read` operations (ADR-015, FR-12).

Every read path carries the rights trail, and none of them calls a model, spends budget,
creates a run or fetches from a museum:

- image URLs appear only for works whose rights status is Open (`open_image_url`);
- the image endpoint serves bytes from refdesk's own cache, Open works only, after
  checking the file against its recorded hash; a work that is not cached is a 404, never a
  fetch at request time;
- search names the retriever it used, and a retriever that cannot load is an explicit
  error (`RetrieverUnavailable`), never a silent switch to another retriever;
- provenance rows come from the export pack's own column builder (`rights_columns`) and
  say they are a rights record, not an approved export.

Museum text is untrusted (PRD 13): it is returned as data, verbatim, and never
interpreted here.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from refdesk.api.models import (
    ProvenanceRow,
    RecordView,
    RightsView,
    SearchHit,
    SearchRequest,
    SearchResults,
)
from refdesk.boards import BoardService, UnknownAnchor
from refdesk.provenance import open_image_url, rights_columns
from refdesk.retrieval import Query
from refdesk.schema import ArtworkRecord, RightsStatus
from refdesk.store import Store
from refdesk.wording import NOT_LEGAL_ADVICE, RIGHTS_RECORD_NOT_EXPORT


class UnknownRecord(KeyError):
    """No record with this ID in the store."""


class RetrieverUnavailable(RuntimeError):
    def __init__(self, retriever: str, detail: str):
        super().__init__(f"Retriever '{retriever}' could not load: {detail}. No other "
                         "retriever was used.")
        self.retriever = retriever


class ImageRefused(Exception):
    """The image cannot be served. `status` is 403 (not an Open work) or 404 (no cached
    file); `reason` says which."""

    def __init__(self, status: int, code: str, reason: str):
        super().__init__(reason)
        self.status, self.code, self.reason = status, code, reason


def _record(service: BoardService, record_id: str) -> ArtworkRecord:
    record = service.records().get(record_id)
    if record is None:
        raise UnknownRecord(record_id)
    return record


def get_record(service: BoardService, record_id: str) -> RecordView:
    record = _record(service, record_id)
    return RecordView(
        id=record.id,
        title=record.title,
        artist=record.artist,
        date=record.date,
        source=record.source,
        object_id=record.object_id,
        record_url=record.record_url,
        rights_status=record.rights.status,
        image_url=open_image_url(record),
    )


def get_rights(service: BoardService, record_id: str) -> RightsView:
    record = _record(service, record_id)
    rights = record.rights
    return RightsView(
        record_id=record.id,
        status=rights.status,  # read from the stored record; unverified stays unverified
        flag_field=rights.flag_field,
        flag_value=rights.flag_value,
        licence_string=rights.licence_string,
        credit_line=record.credit_line,
        checked_at=rights.checked_at,
        not_legal_advice=NOT_LEGAL_ADVICE,
    )


def search(service: BoardService, request: SearchRequest) -> SearchResults:
    """Rank records for a query. Raises UnknownAnchor, ConditionNotUnderstood or
    RetrieverUnavailable."""
    records = service.records()
    if request.anchor_id is not None and request.anchor_id not in records:
        raise UnknownAnchor(request.anchor_id)
    conditions = {k: v for k, v in request.conditions.model_dump().items() if v}
    if service._check_conditions is not None:
        service._check_conditions(conditions)  # ConditionNotUnderstood
    try:
        retriever = service.retriever()
    except Exception as error:  # noqa: BLE001 - any load failure is reported, never hidden
        raise RetrieverUnavailable(
            service.retriever_name, f"{type(error).__name__}: {error}"
        ) from error
    query = Query(
        brief=request.query, conditions=conditions, anchor_id=request.anchor_id, k=request.k
    )
    hits = []
    for hit in retriever.search(query):
        record = records[hit.record_id]
        hits.append(
            SearchHit(
                record_id=record.id,
                title=record.title,
                artist=record.artist,
                date=record.date,
                rights_status=record.rights.status,
                credit_line=record.credit_line,
                image_url=open_image_url(record),
                score=hit.score,
            )
        )
    return SearchResults(retriever=service.retriever_name, hits=hits)


def cached_image(service: BoardService, record_id: str) -> Path:
    """The cached image file for an Open work. Raises UnknownRecord or ImageRefused."""
    record = _record(service, record_id)
    if record.rights.status is not RightsStatus.OPEN:
        raise ImageRefused(
            403,
            "not_open",
            f"Rights status is {record.rights.status.value!r}: images are served for Open "
            "works only.",
        )
    store = Store(service.metadata_path)
    try:
        row = store.get_image(record_id)
    finally:
        store.close()
    not_cached = ImageRefused(
        404,
        "image_not_cached",
        "No cached image for this work. refdesk never fetches from the museum at request "
        "time; use record_url or image_url instead.",
    )
    if row is None:
        raise not_cached
    root = service.images_dir.resolve()
    path = (root / row["path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise not_cached
    if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
        raise ImageRefused(
            404, "image_hash_mismatch", "The cached file does not match its recorded hash."
        )
    return path


def provenance(service: BoardService, record_ids: list[str]) -> list[ProvenanceRow]:
    """One rights record per ID, in the order asked. Raises UnknownRecord with every
    unknown ID, before any row is built."""
    records = service.records()
    unknown = [i for i in record_ids if i not in records]
    if unknown:
        raise UnknownRecord(unknown)
    return [
        ProvenanceRow(notice=RIGHTS_RECORD_NOT_EXPORT, **rights_columns(records[i]))
        for i in record_ids
    ]
