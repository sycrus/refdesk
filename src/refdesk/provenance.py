"""The rights trail of one record, as columns (issue #200; PRD 9, FR-10).

`rights_columns` is the one builder for the record-level, rights-related columns of a
provenance pack. Two callers use it:

- the export pack (`BoardService._pack_row`, G5), which adds the run, review, model and
  approval columns around it;
- `POST /provenance` (a `read` operation), which returns these columns alone, marked as a
  rights record and not an approved export.

What breaks without it: the read endpoint would keep its own copy of the columns, and the
two would drift, so an MCP client could show a rights trail that differs from the one an
approved export writes.

`open_image_url` is the image-URL rule every read path applies: a URL only for works whose
rights status is Open. The adapters already enforce this; the read API checks again, so a
record that somehow carries a URL for a non-open work never leaks it.
"""

from __future__ import annotations

from refdesk.schema import ArtworkRecord, RightsStatus
from refdesk.wording import NOT_LEGAL_ADVICE

# In export-pack order. Every name is also in boards.PACK_COLUMNS (a test pins this).
RIGHTS_COLUMNS = (
    "item_id", "title", "artist", "date", "source", "object_id", "record_url",
    "rights_status", "flag_field", "flag_value", "licence_string", "credit_line",
    "checked_at", "not_legal_advice",
)  # fmt: skip


def rights_columns(record: ArtworkRecord) -> dict[str, str]:
    """The record's own values, verbatim; missing values are empty, never filled in."""
    rights = record.rights
    return {
        "item_id": record.id,
        "title": record.title or "",
        "artist": record.artist or "",
        "date": record.date or "",
        "source": record.source,
        "object_id": record.object_id,
        "record_url": record.record_url or "",
        "rights_status": rights.status.value,
        "flag_field": rights.flag_field or "",
        "flag_value": "" if rights.flag_value is None else str(rights.flag_value),
        "licence_string": rights.licence_string or "",
        "credit_line": record.credit_line or "",
        "checked_at": rights.checked_at.isoformat(),
        "not_legal_advice": NOT_LEGAL_ADVICE,
    }


def open_image_url(record: ArtworkRecord) -> str | None:
    """The image URL, only when the source states the work is open."""
    return record.image_url if record.rights.status is RightsStatus.OPEN else None
