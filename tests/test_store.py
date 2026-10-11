"""SQLite store and ingest: idempotent (no duplicates) and resumable (PRD 10, issue #8)."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from refdesk.ingest import ingest, rebuild
from refdesk.schema import ArtworkRecord, RightsStatus
from refdesk.sources import met
from refdesk.store import Store

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "met"
CHECKED = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
OPEN = json.loads((FIXTURES / "object_436535_open_painting.json").read_text("utf-8"))["body"]


def painting(object_id, **changes):
    return copy.deepcopy(OPEN) | {"objectID": object_id} | changes


class UrlTransport:
    """Answers by URL, counts object fetches, and can fail on chosen object IDs."""

    def __init__(self, objects, fail_on=()):
        self.objects = objects
        self.fail_on = set(fail_on)
        self.fetched = []

    def get_json(self, url):
        if "departmentIds=" in url:
            return 200, {"total": len(self.objects), "objectIDs": list(self.objects)}
        object_id = int(url.rsplit("/", 1)[1])
        if object_id in self.fail_on:
            return 503, "unavailable"
        self.fetched.append(object_id)
        if object_id not in self.objects:
            return 404, {"message": "Not a valid object"}
        return 200, self.objects[object_id]


def source(transport):
    client = met.MetClient(transport, min_interval=0, max_retries=0, sleep=lambda s: None)
    return met.MetSource(client, now=lambda: CHECKED)


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "refdesk.sqlite") as s:
        yield s


OBJECTS = {
    1: painting(1),
    2: painting(2, isPublicDomain=False, rightsAndReproduction="© Someone"),
    3: painting(3, classification="Sculpture"),
}


class TestIdempotent:
    def test_ingesting_twice_creates_no_duplicates(self, store):
        transport = UrlTransport(OBJECTS)
        first = ingest(store, source(transport))
        second = ingest(store, source(transport))
        assert store.count_records() == 2  # object 3 is skipped (not a painting)
        assert first.ingested == 2 and second.ingested == 0
        assert transport.fetched == [1, 2, 3]  # the second run fetched nothing

    def test_refresh_refetches_but_still_has_no_duplicates(self, store):
        transport = UrlTransport(OBJECTS)
        ingest(store, source(transport))
        result = ingest(store, source(transport), refresh=True)
        assert result.ingested == 2
        assert store.count_records() == 2
        assert transport.fetched == [1, 2, 3, 1, 2, 3]

    def test_refresh_updates_a_changed_record_in_place(self, store):
        ingest(store, source(UrlTransport(OBJECTS)))
        changed = OBJECTS | {1: painting(1, title="Retitled by the museum")}
        ingest(store, source(UrlTransport(changed)), refresh=True)
        assert store.get_record("met:1").title == "Retitled by the museum"
        assert store.count_records() == 2


class TestResumable:
    def test_resumes_after_an_interruption_without_refetching(self, store):
        failing = UrlTransport(OBJECTS, fail_on={2})
        with pytest.raises(met.MetUnavailable):
            ingest(store, source(failing))
        assert store.count_records() == 1  # object 1 was committed before the failure

        healthy = UrlTransport(OBJECTS)
        result = ingest(store, source(healthy))
        assert healthy.fetched == [2, 3]  # object 1 is not fetched again
        assert result.ingested == 1
        assert store.count_records() == 2

    def test_skipped_and_missing_objects_are_remembered(self, store):
        # Object 4 is requested but does not exist at the source (404).
        objects = {1: painting(1), 3: painting(3, classification="Sculpture")}
        ingest(store, source(UrlTransport(objects)), object_ids=[1, 3, 4])
        again = UrlTransport(objects)
        ingest(store, source(again), object_ids=[1, 3, 4])
        assert again.fetched == []
        assert store.progress_counts("met") == {
            "done": 1,
            "skipped:classification:Sculpture": 1,
            "skipped:not_found": 1,
        }


class TestStoredContent:
    def test_record_round_trips(self, store):
        ingest(store, source(UrlTransport(OBJECTS)))
        record = store.get_record("met:2")
        assert isinstance(record, ArtworkRecord)
        assert record.rights.status is RightsStatus.PERMISSION_REQUIRED
        assert record.rights.licence_string == "© Someone"

    def test_raw_response_is_stored_under_raw_record_ref(self, store):
        ingest(store, source(UrlTransport(OBJECTS)))
        record = store.get_record("met:1")
        assert store.get_raw(record.raw_record_ref) == OBJECTS[1]

    def test_counts_by_rights_status(self, store):
        ingest(store, source(UrlTransport(OBJECTS)))
        assert store.count_by_rights_status() == {
            "Open (as stated by source)": 1,
            "Permission required": 1,
        }

    def test_limit_stops_after_n_new_objects(self, store):
        transport = UrlTransport(OBJECTS)
        ingest(store, source(transport), limit=1)
        assert transport.fetched == [1]


class TestRecheckSkipped:
    def test_recheck_refetches_only_objects_skipped_for_a_now_included_classification(self, store):
        objects = {
            1: painting(1),
            5: painting(5, classification="Miniatures"),
            6: painting(6, classification="Drawings"),
        }
        narrow = met.MetSource(
            met.MetClient(UrlTransport(objects), min_interval=0, max_retries=0),
            classifications={"Paintings"},
            now=lambda: CHECKED,
        )
        ingest(store, narrow)
        assert store.count_records() == 1

        transport = UrlTransport(objects)
        wide = source(transport)  # default: painting-like classifications
        result = ingest(store, wide, recheck_skipped=True)
        assert transport.fetched == [5]  # not 1 (done) and not 6 (still excluded)
        assert result.ingested == 1
        assert store.count_records() == 2


def test_iter_records_returns_every_record_in_id_order(store):
    ingest(store, source(UrlTransport(OBJECTS)))
    assert [r.id for r in store.iter_records("met")] == ["met:1", "met:2"]


class TestRebuild:
    def test_rebuild_rederives_records_from_stored_raw_without_network(self, store):
        ingest(store, source(UrlTransport(OBJECTS)))
        # Simulate records written by the old mapping, which dropped the years.
        old = store.get_record("met:1").model_copy(update={"date_begin": None, "date_end": None})
        store.save(old, store.get_raw(old.raw_record_ref))
        assert store.get_record("met:1").date_begin is None

        result = rebuild(store, "met")
        record = store.get_record("met:1")
        assert (record.date_begin, record.date_end) == (1889, 1889)
        assert record.rights.checked_at == old.rights.checked_at  # rights were not re-checked
        assert result.rebuilt == 2 and store.count_records() == 2
