"""Normalised artwork record and its rights record (PRD FR-1, FR-2).

Every source adapter produces `ArtworkRecord`s. The schema enforces the rights rules
that must hold no matter which adapter wrote the record:

- a record cannot exist without a rights record;
- "open" can only be stored when it was read from a structured source field;
- unknown rights are "unverified", never guessed (CLAUDE.md hard rules).

What breaks without it: an adapter bug could store an open status with nothing behind
it, and the UI would show it with the same badge as a real one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator, model_validator

from refdesk.wording import RightsStatus  # re-exported; the wording lives in one file

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RightsRecord(_Frozen):
    """What the source states about rights, and where it says it. Not legal advice."""

    source: NonEmpty
    object_id: NonEmpty
    flag_field: str | None  # the structured field the status was read from, e.g. "isPublicDomain"
    flag_value: str | bool | None  # its raw value, exactly as the source returned it
    licence_string: str | None
    checked_at: datetime
    status: RightsStatus

    @field_validator("checked_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("checked_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _open_needs_a_structured_flag(self) -> RightsRecord:
        has_flag = self.flag_field is not None and self.flag_value is not None
        if self.status is RightsStatus.OPEN and not has_flag:
            raise ValueError(
                "status 'open' must be read from a structured source field (FR-2): "
                "set flag_field and flag_value, or use status 'unverified'"
            )
        return self

    @classmethod
    def unverified(cls, *, source: str, object_id: str, checked_at: datetime) -> RightsRecord:
        """The record for a source that gave no usable rights flag."""
        return cls(
            source=source,
            object_id=object_id,
            flag_field=None,
            flag_value=None,
            licence_string=None,
            checked_at=checked_at,
            status=RightsStatus.UNVERIFIED,
        )


class ArtworkRecord(_Frozen):
    """One artwork from one source, normalised. Descriptive fields stay None when the
    source does not give them; they are never filled in from memory."""

    id: NonEmpty  # "<source>:<object_id>"
    source: NonEmpty
    object_id: NonEmpty
    title: str | None = None
    artist: str | None = None
    date: str | None = None  # the source's display date, verbatim
    date_begin: int | None = None  # structured start year from the source (negative = BCE)
    date_end: int | None = None  # structured end year from the source
    medium: str | None = None
    classification: str | None = None
    subject_tags: tuple[str, ...] = ()
    image_url: str | None = None
    record_url: str | None = None
    raw_record_ref: NonEmpty  # where the raw source response is stored
    rights: RightsRecord

    @model_validator(mode="after")
    def _consistent_identity(self) -> ArtworkRecord:
        if self.id != f"{self.source}:{self.object_id}":
            raise ValueError(f"id must be '{self.source}:{self.object_id}'")
        if None not in (self.date_begin, self.date_end) and self.date_begin > self.date_end:
            raise ValueError("date_begin must not be after date_end")
        if (self.rights.source, self.rights.object_id) != (self.source, self.object_id):
            raise ValueError("rights record belongs to a different object")
        return self
