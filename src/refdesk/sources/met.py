"""The Met Collection API adapter: European Paintings slice (PRD 9, docs/data-sources.md).

Three parts, kept separate so each can be tested on its own:

- `to_record()`: pure mapping from one raw object to an `ArtworkRecord`. This holds the
  rights logic, so it never touches the network.
- `MetClient`: polite HTTP. It spaces requests (default 1/s; the documented cap is 80/s and
  the API sends no rate-limit headers, so we throttle ourselves), and retries 429 and 5xx
  with exponential backoff. Clock, sleep and transport are injected for tests.
- `MetSource`: lists a department's object IDs and yields records, counting what it
  skipped and why.

Rights rule (from the source's structured field only, never inferred):
  isPublicDomain is True  -> Open (as stated by source)
  isPublicDomain is False -> Permission required  (the Met does not release it; it also
                                                   withholds the image)
  missing or not a bool   -> Unverified
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus

SOURCE = "met"
BASE_URL = "https://collectionapi.metmuseum.org/public/collection"
OBJECTS_PATH = "/v1/objects"
SEARCH_PATH = "/v1.1/search"  # v1/search was retired on 2026-10-01 (returns 410)
PAINTINGS_DEPARTMENT_ID = 11  # "European Paintings"
# Painting-like classifications kept in the slice (Joe, 2026-10-11). Department 11 also
# holds drawings and manuscripts, which are skipped with the reason recorded.
PAINTING_CLASSIFICATIONS = frozenset({"Paintings", "Miniatures", "Pastels & Oil Sketches on Paper"})
FLAG_FIELD = "isPublicDomain"
USER_AGENT = "refdesk/0.1 (research project; github.com/sycrus/refdesk)"


class MetError(Exception):
    pass


class MetUnavailable(MetError):
    """Retries exhausted (rate limited or server errors)."""


class MetNotFound(MetError):
    pass


def _text(raw: dict[str, Any], key: str) -> str | None:
    # The Met uses "" for missing values. Store None, never a placeholder.
    value = raw.get(key)
    if isinstance(value, str):
        value = value.strip()
    return value or None


def _year(raw: dict[str, Any], key: str) -> int | None:
    # Structured years from the source. Only real integers count (bool is an int subclass).
    value = raw.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _rights(raw: dict[str, Any], checked_at: datetime) -> RightsRecord:
    object_id = str(raw["objectID"])
    if FLAG_FIELD not in raw:
        return RightsRecord.unverified(source=SOURCE, object_id=object_id, checked_at=checked_at)
    value = raw[FLAG_FIELD]
    if value is True:
        status = RightsStatus.OPEN
    elif value is False:
        status = RightsStatus.PERMISSION_REQUIRED
    else:
        # Present but not a boolean ("true", 1, null): the flag is unclear, so not open.
        status = RightsStatus.UNVERIFIED
    return RightsRecord(
        source=SOURCE,
        object_id=object_id,
        flag_field=FLAG_FIELD,
        flag_value=value if isinstance(value, bool | str) else None,
        # The API has no licence field. CC0 comes from the Met's Open Access policy
        # (docs/data-sources.md); rightsAndReproduction holds copyright notices only.
        licence_string=_text(raw, "rightsAndReproduction"),
        checked_at=checked_at,
        status=status,
    )


def to_record(raw: dict[str, Any], *, checked_at: datetime) -> ArtworkRecord:
    object_id = str(raw["objectID"])
    rights = _rights(raw, checked_at)
    artist = " ".join(p for p in (_text(raw, "artistPrefix"), _text(raw, "artistDisplayName")) if p)
    image = _text(raw, "primaryImageSmall") or _text(raw, "primaryImage")
    return ArtworkRecord(
        id=f"{SOURCE}:{object_id}",
        source=SOURCE,
        object_id=object_id,
        title=_text(raw, "title"),
        artist=artist or None,
        date=_text(raw, "objectDate"),
        date_begin=_year(raw, "objectBeginDate"),
        date_end=_year(raw, "objectEndDate"),
        medium=_text(raw, "medium"),
        classification=_text(raw, "classification"),
        subject_tags=tuple(t["term"] for t in (raw.get("tags") or []) if t.get("term")),
        # Store an image link only for open works (design system: permission-required
        # works show metadata and a link, never the image).
        image_url=image if rights.status is RightsStatus.OPEN else None,
        record_url=_text(raw, "objectURL"),
        raw_record_ref=f"{SOURCE}/objects/{object_id}.json",
        rights=rights,
    )


class Transport(Protocol):
    def get_json(self, url: str) -> tuple[int, Any]: ...

    def get_bytes(self, url: str) -> tuple[int, bytes]: ...


class UrllibTransport:
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    def get_json(self, url: str) -> tuple[int, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8", errors="replace")

    def get_bytes(self, url: str) -> tuple[int, bytes]:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, b""


# Image URLs come from museum records, which are untrusted input (CLAUDE.md). Only fetch
# from the Met's own image host.
IMAGE_HOSTS = frozenset({"images.metmuseum.org"})


class MetClient:
    DEFAULT_MIN_INTERVAL = 1.0  # seconds between requests; documented cap is 80/s
    RETRY_STATUSES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        transport: Transport | None = None,
        *,
        min_interval: float = DEFAULT_MIN_INTERVAL,
        max_retries: int = 3,
        backoff: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.transport = transport or UrllibTransport()
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.backoff = backoff
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def _throttle(self) -> None:
        if self._last is not None:
            wait = self.min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        self._last = self._clock()

    def get(self, path: str) -> Any:
        return self._request(BASE_URL + path, self.transport.get_json)

    def get_bytes(self, url: str) -> bytes:
        """Fetch an image, with the same throttle and backoff. Met image host only."""
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in IMAGE_HOSTS:
            raise ValueError(f"refusing to fetch from {parts.hostname!r}: not a Met image host")
        # Some Met image paths contain spaces ("SF 11.126.2.jpg"). Percent-encode the path;
        # unquote first so an already-encoded path is not encoded twice.
        path = urllib.parse.quote(urllib.parse.unquote(parts.path), safe="/")
        return self._request(parts._replace(path=path).geturl(), self.transport.get_bytes)

    def _request(self, url: str, fetch: Callable[[str], tuple[int, Any]]) -> Any:
        for attempt in range(self.max_retries + 1):
            self._throttle()
            status, body = fetch(url)
            if status == 200:
                return body
            if status == 404:
                raise MetNotFound(url)
            if status not in self.RETRY_STATUSES or attempt == self.max_retries:
                break
            self._sleep(self.backoff * 2**attempt)
        raise MetUnavailable(f"{status} from {url} after {attempt + 1} attempt(s)")

    def get_object(self, object_id: int) -> dict[str, Any]:
        return self.get(f"{OBJECTS_PATH}/{object_id}")

    def list_object_ids(self, department_id: int) -> list[int]:
        return self.get(f"{OBJECTS_PATH}?departmentIds={department_id}").get("objectIDs") or []


@dataclass(frozen=True)
class Fetched:
    record: ArtworkRecord
    raw: dict[str, Any]


@dataclass(frozen=True)
class Skipped:
    object_id: int
    reason: str  # "not_found" or "classification:<value>"


@dataclass
class SourceStats:
    ingested: int = 0
    open: int = 0
    skipped: Counter = field(default_factory=Counter)


class MetSource:
    """European Paintings slice: department 11, painting-like classifications."""

    def __init__(
        self,
        client: MetClient | None = None,
        *,
        department_id: int = PAINTINGS_DEPARTMENT_ID,
        classifications: frozenset[str] | set[str] = PAINTING_CLASSIFICATIONS,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.client = client or MetClient()
        self.department_id = department_id
        self.classifications = frozenset(classifications)
        self._now = now
        self.stats = SourceStats()

    def list_object_ids(self) -> list[int]:
        return self.client.list_object_ids(self.department_id)

    def fetch_one(self, object_id: int) -> Fetched | Skipped:
        """Fetch one object. Every ID gets an outcome, so the ingest can mark skips as done.

        MetUnavailable is not caught: the caller stops, and resumes later."""
        try:
            raw = self.client.get_object(object_id)
        except MetNotFound:
            outcome: Fetched | Skipped = Skipped(object_id, "not_found")
        else:
            if raw.get("classification") not in self.classifications:
                reason = f"classification:{raw.get('classification') or 'none'}"
                outcome = Skipped(object_id, reason)
            else:
                outcome = Fetched(to_record(raw, checked_at=self._now()), raw)
        if isinstance(outcome, Skipped):
            self.stats.skipped[outcome.reason] += 1
        else:
            self.stats.ingested += 1
            self.stats.open += outcome.record.rights.status is RightsStatus.OPEN
        return outcome

    def iter_items(
        self, object_ids: list[int] | None = None
    ) -> Iterator[tuple[ArtworkRecord, dict]]:
        """Yield (record, raw response), so the store can keep the raw record (FR-1)."""
        for object_id in self.list_object_ids() if object_ids is None else object_ids:
            outcome = self.fetch_one(object_id)
            if isinstance(outcome, Fetched):
                yield outcome.record, outcome.raw

    def iter_records(self, object_ids: list[int] | None = None) -> Iterator[ArtworkRecord]:
        for record, _ in self.iter_items(object_ids):
            yield record
